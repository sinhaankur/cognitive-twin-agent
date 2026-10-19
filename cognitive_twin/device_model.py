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

# How long Ollama keeps an idle model loaded. This is the single biggest lever on
# how FAST she feels: if the model gets evicted between turns, every turn pays the
# cold-load cost (tens of seconds on a 6GB model — "why is she so slow"). If the
# machine has ample RAM, there's no reason to evict a small chat model, so we keep
# it resident much longer; only on tight machines do we unload promptly to let the
# box breathe. Override with CTWIN_KEEP_ALIVE ("30m", "0" = unload now, "-1" = pin
# forever). A companion should answer in a beat, not reload her brain each time.
def _default_keep_alive() -> str:
    try:
        import subprocess as _sp
        gb = int(_sp.run(["sysctl", "-n", "hw.memsize"], capture_output=True,
                         text=True, timeout=3).stdout.strip()) / (1024 ** 3)
    except Exception:
        gb = 16  # unknown → assume a middling machine
    if gb >= 24:
        return "2h"     # roomy (a small chat model is a rounding error) → stay warm
    if gb >= 12:
        return "30m"    # comfortable → warm across a working session
    return "5m"         # tight → unload promptly so the machine breathes


KEEP_ALIVE: str = os.environ.get("CTWIN_KEEP_ALIVE", "").strip() or _default_keep_alive()

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


# Cache of model name → on-disk size in GB (from Ollama /api/tags), so a single
# pick doesn't re-query per candidate.
_SIZE_CACHE: dict[str, float] = {}


def _model_sizes_gb() -> dict[str, float]:
    """Each installed model's size in GB, from Ollama's /api/tags (best-effort)."""
    if _SIZE_CACHE:
        return _SIZE_CACHE
    try:
        import json as _json
        import urllib.request as _url
        host = os.environ.get("CTWIN_OLLAMA_HOST") or "http://localhost:11434"
        with _url.urlopen(host.rstrip("/") + "/api/tags", timeout=4) as r:
            data = _json.loads(r.read() or b"{}")
        for m in data.get("models", []):
            name = m.get("name") or m.get("model")
            size = m.get("size")
            if name and isinstance(size, (int, float)):
                _SIZE_CACHE[name] = float(size) / (1024 ** 3)
    except Exception:
        pass
    return _SIZE_CACHE


def _model_fits(name: str, ram_gb: float) -> bool:
    """Does `name` fit comfortably in RAM? A model needs its own weights PLUS
    headroom for the KV-cache and the OS; a model bigger than ~55% of total RAM
    will swap and feel frozen. If we can't read the size (first run, Ollama down),
    assume it fits so we never block her from starting."""
    sizes = _model_sizes_gb()
    gb = sizes.get(name)
    if gb is None:
        return True            # unknown → don't block
    # leave room for the OS + app + KV-cache: the model should be ≲55% of total RAM
    return gb <= max(2.0, ram_gb * 0.55)


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
    # Prefer Vera's OWN trained model when it's installed AND it comfortably FITS
    # this machine. The catch: her model is a 3B, but an UNQUANTIZED (F16) build is
    # ~6.5 GB — that does NOT fit an 8 GB Mac, where it swaps and feels frozen (the
    # "not awake" bug on base specs). So we size-check the installed Vera model and
    # only pick it when the RAM can hold it; on a tight machine we prefer a
    # quantized Vera tag if one's pulled, else fall through to the small base tiers.
    for vm in _VERA_MODELS:
        matches = [vm] if vm in inst else []
        base = vm.split(":")[0]
        matches += [i for i in installed if i.split(":")[0] == base and i != vm]
        if not matches:
            continue
        # among the installed variants of this Vera model, pick the largest one
        # that fits the RAM (quantized tags are smaller than F16) — fits() reads
        # Ollama's reported size; on tight RAM an F16 build is skipped.
        fitting = [m for m in matches if _model_fits(m, ram_gb)]
        if fitting:
            # prefer the exact canonical tag when it fits, else any fitting variant
            return vm if vm in fitting else fitting[0]
        # her model is installed but too big for this RAM → fall through to a
        # smaller base below rather than pick a model that will thrash.
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


def recommend_pull(ram_gb: float | None = None) -> str:
    """The ONE model the installer should pull for THIS machine on first run —
    the smallest model that's genuinely capable for the RAM it has, so the
    download stays as light as the hardware allows while still working well.

    This is what makes "install it easily + don't take much space" true: an 8 GB
    Mac pulls a ~1 GB 3B, not a 4.7 GB 7B it can't comfortably run. Her own
    trained `vera-tuned` (a light 3B, ~1.9 GB) is preferred on any machine with
    room for it, because it's genuinely *her* and still small.
    """
    if ram_gb is None:
        ram_gb = total_ram_gb()
    # Her trained model is a 3B — great on 12 GB+; on a tight machine fall to the
    # smallest capable base so the first-run download is as small as possible.
    if ram_gb >= 12:
        return "vera-tuned"          # ~1.9 GB, her voice, runs well on 16 GB+
    if ram_gb >= 8:
        return "qwen2.5:3b"          # ~1.9 GB base; tight but workable on 8 GB
    return "qwen2.5:1.5b"            # smallest capable fallback (~1 GB)
