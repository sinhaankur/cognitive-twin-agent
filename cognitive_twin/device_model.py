"""
Device-aware model selection — one LLM, sized to THIS machine.

Vera runs on many devices (a 16 GB laptop, a 32 GB desktop, an iPhone bridge).
A hardcoded 14B default is wrong for most of them: it pins ~15 GB of RAM and makes
the machine struggle. This module picks the best LOCAL chat model the machine can
comfortably hold, from the models actually installed, so only ONE right-sized LLM
runs.

It also centralises two footprint knobs:
  * KEEP_ALIVE  — how long Ollama keeps an idle model in RAM before unloading it.
                  Short, so Vera doesn't leave a big model resident after a reply.
  * is_embedder — so embedding-only models (nomic-embed-text) never show up as a
                  chat choice (they can't answer) and are never auto-loaded as one.

Everything is best-effort and offline: if we can't read RAM or list models, we
fall back to a safe small default. No cloud, no new dependency.
"""

from __future__ import annotations

import os
import shutil
import subprocess

# How long Ollama keeps an idle model loaded. Keeping it short means a heavy model
# doesn't sit in RAM after you're done — the machine breathes again between turns.
# Override with CTWIN_KEEP_ALIVE (e.g. "30m", "0" to unload immediately, "-1" to
# pin forever). Default: 5 minutes — warm enough for a conversation, gone when idle.
KEEP_ALIVE: str = os.environ.get("CTWIN_KEEP_ALIVE", "5m").strip() or "5m"

# Embedding-only models — they produce vectors, not chat. They must never be
# offered as, or auto-selected as, the chat model (picking one makes Vera error).
_EMBED_HINTS = ("embed", "embedding", "nomic-embed", "bge-", "mxbai-embed", "snowflake-arctic-embed")

# Vera's OWN trained models, best first. If one of these is installed we prefer it
# over a generic base — it's her: warm, in-character, and LIGHT (3B), so it runs
# well on EVERY device, not just roomy ones. This is what makes the app feel like
# Vera out of the box instead of a generic assistant. Falls through to the RAM
# tiers below only when none of these are pulled.
_VERA_MODELS: tuple[str, ...] = ("vera-merged", "vera-tuned", "empathia")

# Preferred LOCAL chat models, smallest-capable first within each tier. We pick the
# largest one that fits the machine's RAM AND is installed. Tool-calling capable
# families only (so the agent's tools keep working).
#   tier → (min GB of total RAM we want before choosing it, candidate model ids)
_TIERS: list[tuple[int, tuple[str, ...]]] = [
    (48, ("qwen2.5:14b", "llama3.1:8b", "qwen2.5:7b")),   # roomy desktop
    (24, ("qwen2.5:7b", "llama3.1:8b", "qwen2.5:3b")),    # 32 GB laptop → 7B, not 14B
    (12, ("qwen2.5:3b", "llama3.2:3b", "qwen2.5:7b")),    # 16 GB machine
    (0,  ("qwen2.5:3b", "llama3.2:3b", "qwen2.5:1.5b")),  # small / fallback
]

# A safe default if nothing is installed yet (first run, before `ollama pull`).
_SAFE_DEFAULT = "qwen2.5:7b"


def is_embedder(name: str) -> bool:
    """True if `name` looks like an embedding-only model (not a chat model)."""
    n = (name or "").lower()
    return any(h in n for h in _EMBED_HINTS)


def total_ram_gb() -> float:
    """Physical RAM in GB (best-effort; 16 if we can't tell)."""
    # Linux: os.sysconf; macOS: sysctl hw.memsize
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page = os.sysconf("SC_PAGE_SIZE")
        if pages > 0 and page > 0:
            return (pages * page) / (1024 ** 3)
    except (ValueError, OSError, AttributeError):
        pass
    try:
        if shutil.which("sysctl"):
            out = subprocess.run(
                ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=3
            ).stdout.strip()
            if out.isdigit():
                return int(out) / (1024 ** 3)
    except (OSError, subprocess.SubprocessError):
        pass
    return 16.0  # conservative middle ground


def _installed_chat_models() -> list[str]:
    """Chat models installed in Ollama (embedders filtered out)."""
    try:
        from .llm.ollama_client import OllamaClient
        host = os.environ.get("CTWIN_OLLAMA_HOST") or "http://localhost:11434"
        names = OllamaClient(host=host).available_models()
    except Exception:
        names = []
    return [n for n in names if n and not is_embedder(n)]


def pick_default(installed: list[str] | None = None, ram_gb: float | None = None,
                 *, query_ollama: bool = False) -> str:
    """The best chat model for THIS machine.

    An explicit CTWIN_MODEL always wins (the user pinned it). Otherwise choose the
    largest model that fits the RAM tier. By default this is FAST and NON-BLOCKING:
    it picks purely from the RAM tier (no subprocess, no network) so it can run on
    the server's startup path without ever stalling the port bind — the bug where a
    busy Ollama made the voice server hang before `serve_forever()`.

    Pass query_ollama=True (or an explicit `installed` list) to also prefer models
    actually pulled — used by non-startup callers (e.g. the picker) where a short
    Ollama query is fine.
    """
    env = os.environ.get("CTWIN_MODEL", "").strip()
    if env:
        return env
    if ram_gb is None:
        ram_gb = total_ram_gb()
    # Fast path: no installed-list given and we weren't asked to query Ollama →
    # choose by RAM tier alone. Never touches the network, so startup can't hang.
    if installed is None and not query_ollama:
        for floor, candidates in _TIERS:
            if ram_gb >= floor:
                return candidates[0]
        return _SAFE_DEFAULT
    if installed is None:
        installed = _installed_chat_models()
    inst = set(installed)
    # Prefer Vera's OWN trained model when it's installed — it's her, and it's
    # light (3B) so it suits every device. Only once we know what's installed
    # (this branch) so we never pick a model that isn't pulled.
    for vm in _VERA_MODELS:
        if vm in inst:
            return vm
        base = vm.split(":")[0]
        for i in installed:
            if i.split(":")[0] == base:
                return i
    for floor, candidates in _TIERS:
        if ram_gb >= floor:
            for m in candidates:
                if m in inst or m.split(":")[0] in {i.split(":")[0] for i in inst}:
                    # prefer the exact tag if present, else the matching base
                    if m in inst:
                        return m
                    base = m.split(":")[0]
                    for i in installed:
                        if i.split(":")[0] == base:
                            return i
            # tier matched RAM but none installed — keep scanning smaller tiers
    # nothing from the tiers is installed: use any installed chat model, else safe
    return installed[0] if installed else _SAFE_DEFAULT
