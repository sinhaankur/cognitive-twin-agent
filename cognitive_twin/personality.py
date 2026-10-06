"""
Personality dials — small, user-tunable knobs on Vera's TONE (not her identity).

The warm-companion character in system_dna.md stays the core; these just modulate
how she expresses it: how much warmth, humor, and nerdy-playful enthusiasm she
brings. Stored sealed (the kernel), 0.0–1.0 each. A prompt fragment nudges the
model; the identity underneath is unchanged.

Defaults: warm, lightly witty, a little nerdy — her natural setting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_FILE = "personality.json"

# knob → (default, low-description, high-description) for the prompt fragment
_DIALS: dict[str, tuple[float, str, str]] = {
    "warmth": (0.7,
               "a little more reserved and matter-of-fact",
               "especially warm, tender, and affectionate"),
    "humor": (0.4,
              "earnest and sincere, humor only when it's truly earned",
              "quick with a light, kind wit and the occasional joke"),
    "playfulness": (0.45,
                    "calm and grounded",
                    "playful and nerdy-curious — lights up sharing an idea or a "
                    "cool fact, the way an excited friend would"),
}


def _dir() -> Path:
    from . import security
    return security.home()


def load() -> dict[str, float]:
    """The current dial values (sealed read; defaults if unset)."""
    from . import security
    data = security.read_state(_dir() / _FILE, default=None) or {}
    out: dict[str, float] = {}
    for k, (default, _, _) in _DIALS.items():
        v = data.get(k, default)
        try:
            out[k] = max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            out[k] = default
    return out


def save(values: dict[str, Any]) -> dict[str, float]:
    """Update one or more dials (0.0–1.0); unknown keys ignored. Sealed write."""
    from . import security
    cur = load()
    for k in _DIALS:
        if k in values:
            try:
                cur[k] = max(0.0, min(1.0, float(values[k])))
            except (TypeError, ValueError):
                pass
    security.write_state(_dir() / _FILE, cur)
    return cur


def prompt() -> str:
    """A short tone-nudge fragment from the current dials — only mentions a dial
    when it's set meaningfully high or low, so a neutral setting adds nothing."""
    vals = load()
    notes: list[str] = []
    for k, (default, low, high) in _DIALS.items():
        v = vals[k]
        if v >= 0.7:
            notes.append(high)
        elif v <= 0.25:
            notes.append(low)
    if not notes:
        return ""
    return ("TONE (how you express yourself today — your character underneath is "
            "unchanged): be " + "; ".join(notes) + ". Never force it; let it feel "
            "natural, and always read the moment first.")
