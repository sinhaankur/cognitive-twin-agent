"""
presence.py — her sense of you, right now (opt-in camera, on-device).

The voice UI can — only after you click "See me" — run the owner's optical-flow
engine (Shi-Tomasi corners + pyramidal Lucas-Kanade, ported from
sinhaankur.com/lab/optical-flow) on the webcam, entirely in the browser page.
No frame ever leaves the page: the page posts only a handful of derived motion
signals here (how animated you are, a nod, a lean), and this module holds just
the LATEST reading, in process memory.

Ephemeral by design: presence is the present tense. Nothing is written to disk,
nothing enters memory.jsonl, and a reading older than a few seconds is treated
as gone. Honesty rule: these are *motion* facts ("very still", "nodded"), never
invented emotions ("sad") — the agent may respond to what the camera actually
measured, not to a guess dressed as a fact.
"""

from __future__ import annotations

import time
from typing import Any

_STALE_S = 15.0
_last: dict[str, Any] | None = None


def update(sig: dict[str, Any]) -> None:
    """Store the latest derived reading from the (opt-in) camera page."""
    global _last
    _last = {
        "present": bool(sig.get("present")),
        "energy": max(0.0, min(1.0, float(sig.get("energy") or 0.0))),
        "gesture": sig.get("gesture") if sig.get("gesture") in ("nod", "shake") else None,
        "lean": sig.get("lean") if sig.get("lean") in ("in", "out") else None,
        "ts": time.time(),
    }


def stop() -> None:
    """The user turned the camera off — forget immediately."""
    global _last
    _last = None


def current() -> dict[str, Any] | None:
    """The latest reading, or None when off/stale (presence never lingers)."""
    if _last is None or (time.time() - _last["ts"]) > _STALE_S:
        return None
    return dict(_last)


def _energy_word(e: float) -> str:
    if e < 0.08:
        return "very still"
    if e < 0.28:
        return "calm"
    if e < 0.6:
        return "animated"
    return "very animated"


def context_for_prompt() -> str:
    """One honest line for the system prompt — empty when she can't see you."""
    c = current()
    if not c or not c.get("present"):
        return ""
    bits = [_energy_word(c["energy"])]
    if c.get("gesture") == "nod":
        bits.append("just nodded")
    elif c.get("gesture") == "shake":
        bits.append("just shook their head")
    if c.get("lean") == "in":
        bits.append("leaning in")
    elif c.get("lean") == "out":
        bits.append("leaning back")
    return ("Right now you can see the user (their camera, on-device, opt-in): "
            "they look " + ", ".join(bits) + ". These are motion cues only — "
            "respond naturally, never claim to know their feelings from this.")


def status() -> str:
    c = current()
    if not c:
        return "presence: off (opt-in camera not running)"
    return f"presence: seeing you — {_energy_word(c['energy'])}"
