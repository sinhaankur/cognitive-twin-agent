"""
presence.py — her sense of you, right now (opt-in camera, on-device).

Two eyes feed this, both opt-in behind "See me", both fully on-device:
  - the Mac app: Apple Vision face landmarks (FaceEngine.swift) — real facial
    geometry: smile, knitted brow, blink rate, attention, nod/shake, lean
  - the browser page: the owner's optical-flow engine (Shi-Tomasi + pyramidal
    Lucas-Kanade, ported from sinhaankur.com/lab/optical-flow) — motion only

No frame ever leaves the sender: only a handful of derived signals arrive
here, and this module holds just the LATEST reading, in process memory.

Ephemeral by design: presence is the present tense. Nothing is written to disk,
nothing enters memory.jsonl, and a reading older than a few seconds is treated
as gone. Honesty rule: these are *measured* facts — "smiling" is a mouth shape,
"brow knitted" is a distance — never invented emotions ("sad", "stressed");
the agent may respond to what the camera actually measured, not to a guess
dressed as a fact.
"""

from __future__ import annotations

import time
from typing import Any

_STALE_S = 15.0
_last: dict[str, Any] | None = None


def _unit(v: Any) -> float | None:
    """A 0..1 signal, or None when the sender didn't measure it."""
    if v is None:
        return None
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return None


def update(sig: dict[str, Any]) -> None:
    """Store the latest derived reading from the (opt-in) camera sender."""
    global _last
    _last = {
        "present": bool(sig.get("present")),
        "energy": max(0.0, min(1.0, float(sig.get("energy") or 0.0))),
        "gesture": sig.get("gesture") if sig.get("gesture") in ("nod", "shake") else None,
        "lean": sig.get("lean") if sig.get("lean") in ("in", "out") else None,
        # facial geometry — only the app's Vision eye sends these; the browser
        # eye measures motion alone, so they stay None there (honest absence)
        "smile": _unit(sig.get("smile")),
        "brow": _unit(sig.get("brow")),
        "blink_rate": (float(sig["blink_rate"]) if isinstance(sig.get("blink_rate"), (int, float)) else None),
        "attending": (bool(sig["attending"]) if sig.get("attending") is not None else None),
        "source": sig.get("source") if sig.get("source") in ("face", "flow") else "flow",
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
    if (c.get("smile") or 0) >= 0.55:
        bits.append("smiling")
    if (c.get("brow") or 0) >= 0.55:
        bits.append("brow knitted")
    if (c.get("blink_rate") or 0) >= 28:
        bits.append("blinking fast")
    if c.get("attending") is False:
        bits.append("looking away from the screen")
    if c.get("gesture") == "nod":
        bits.append("just nodded")
    elif c.get("gesture") == "shake":
        bits.append("just shook their head")
    if c.get("lean") == "in":
        bits.append("leaning in")
    elif c.get("lean") == "out":
        bits.append("leaning back")
    kind = "face cues" if c.get("source") == "face" else "motion cues"
    return ("Right now you can see the user (their camera, on-device, opt-in): "
            "they look " + ", ".join(bits) + f". These are measured {kind} only — "
            "respond naturally, never claim to know their feelings from this.")


def status() -> str:
    c = current()
    if not c:
        return "presence: off (opt-in camera not running)"
    return f"presence: seeing you — {_energy_word(c['energy'])}"
