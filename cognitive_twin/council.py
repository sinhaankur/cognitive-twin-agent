"""
Twin Council — ask one question, hear every twin answer.

Like voices in your head: you pose a single question and each of your twins —
your mom, your dad, a mentor — answers *as themselves*, from their own persona
and their own private memory. You then see the takes side by side and decide.

How it stays true to the rest of the app: a twin *is* its folder (persona +
memory + voice). Every storage module (persona, memory, soul, voice_profile)
resolves its directory from ``CTWIN_MEMORY_DIR`` / ``CTWIN_PERSONA_DIR`` at call
time — so to "become" a twin we point those env vars at that twin's folder,
build a fresh agent (which reads that twin's persona + memory into its system
prompt), ask, and move on. Each twin thus reasons and speaks as *that* person.

Why sequential, not threaded: those env vars are process-global, so running
twins concurrently in threads would race on them. Running one at a time keeps
each twin's context clean and matches the existing single-agent code exactly.
The whole active-twin selection is saved and restored, so a council never
changes which twin is active afterwards.

This module has no network code and adds no dependencies — it composes the
agent loop you already have, once per twin.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import persona, twins


@dataclass
class TwinTake:
    """One twin's answer to the council question."""
    slug: str            # the twin's folder name (stable id)
    name: str            # display name (persona name if set, else the slug)
    answer: str          # what the twin said
    model: str | None = None   # which local model produced it (for transparency)
    error: str | None = None   # set instead of `answer` if this twin failed


@dataclass
class CouncilResult:
    question: str
    takes: list[TwinTake]

    def ok(self) -> list[TwinTake]:
        return [t for t in self.takes if t.error is None]


def _twin_display_name(slug: str) -> str:
    """The persona name for a twin folder, else the slug. Assumes the env vars
    are already pointed at that twin (so persona.load reads the right file)."""
    try:
        p = persona.load()
        if p.name:
            return p.name
    except Exception:
        pass
    return slug


def _point_env_at(twin_slug: str) -> None:
    """Make persona/memory/soul/voice read the given twin's folder."""
    d = twins._twins_dir() / twin_slug
    os.environ["CTWIN_MEMORY_DIR"] = str(d)
    os.environ["CTWIN_PERSONA_DIR"] = str(d)


def _snapshot_env() -> dict[str, str | None]:
    return {k: os.environ.get(k) for k in ("CTWIN_MEMORY_DIR", "CTWIN_PERSONA_DIR")}


def _restore_env(saved: dict[str, str | None]) -> None:
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def convene(
    question: str,
    *,
    twin_slugs: list[str] | None = None,
    build_agent: Callable[..., object] | None = None,
    ask: Callable[[object, str], tuple[str, dict | None]] | None = None,
    on_progress: Callable[[str, str], None] | None = None,
) -> CouncilResult:
    """Ask `question` of every twin (or the given subset) and gather their takes.

    Runs one twin at a time. For each: point the storage env at that twin, build
    a fresh agent (reads that twin's persona + memory), ask, record the take. The
    active-twin selection and env are fully restored afterwards.

    `build_agent` and `ask` are injected so this is unit-testable without a live
    model; the CLI wires them to the real agent + `_run_once_capture`.
    `on_progress(slug, phase)` is called with phase in {"start", "done", "error"}
    so a caller can show live progress.
    """
    slugs = twin_slugs if twin_slugs is not None else twins.list_twins()
    takes: list[TwinTake] = []
    saved = _snapshot_env()

    # Lazily wire the real agent unless the caller injected its own (tests do).
    if build_agent is None or ask is None:
        from .cli import build_agent as _ba, _run_once_capture as _cap
        build_agent = build_agent or _ba
        ask = ask or _cap

    try:
        for slug in slugs:
            _point_env_at(slug)
            name = _twin_display_name(slug)
            if on_progress:
                on_progress(name, "start")
            try:
                agent = build_agent(None, route=True, interactive_confirm=False)
                answer, route = ask(agent, question)
                model = (route or {}).get("model") if isinstance(route, dict) else None
                takes.append(TwinTake(slug=slug, name=name,
                                      answer=(answer or "").strip(), model=model))
                if on_progress:
                    on_progress(name, "done")
            except Exception as e:  # one twin failing must not sink the council
                takes.append(TwinTake(slug=slug, name=name, answer="",
                                      error=str(e) or e.__class__.__name__))
                if on_progress:
                    on_progress(name, "error")
    finally:
        _restore_env(saved)

    return CouncilResult(question=question, takes=takes)


# ---- rendering ---------------------------------------------------------------
def render(result: CouncilResult, *, width: int = 78) -> str:
    """A readable, side-by-side-ish transcript of the council for the terminal."""
    lines: list[str] = []
    lines.append(f'  council › "{result.question}"')
    lines.append("")
    if not result.takes:
        lines.append("  no twins to ask — create one with `ctwin twin new \"Name\"`.")
        return "\n".join(lines)

    for t in result.takes:
        header = f"  {t.name} »"
        if t.model:
            header += f"   ({t.model})"
        lines.append(header)
        body = t.error and f"[couldn't answer: {t.error}]" or t.answer
        for para in body.splitlines() or [""]:
            for chunk in _wrap(para, width):
                lines.append(f"    {chunk}")
        lines.append("")

    ok = result.ok()
    if len(ok) > 1:
        lines.append(f"  — {len(ok)} voices weighed in. The choice is yours.")
    return "\n".join(lines)


def _wrap(text: str, width: int) -> list[str]:
    """Soft word-wrap a single line to `width`; keeps empty lines as-is."""
    if not text:
        return [""]
    words = text.split(" ")
    out: list[str] = []
    cur = ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    return out
