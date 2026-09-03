"""
principles — how YOU decide, held explicitly, so Vera reasons like your twin.

Vera can track what you do (rhythm, activity) and surface what's timely
(proactive). This is the deeper layer Ankur pointed at with "want vs need,"
"happiness vs experience," "decisions vs mental model": Vera holds the
DECISION PRINCIPLES you actually think and act on, and FRAMES choices through
them — so a suggestion fits how *you'd* genuinely decide, not a generic optimizer.

Two hard rules keep this honest:
  1. **You state them.** Vera doesn't invent your values or silently infer them
     and put words in your mouth. You add/edit/remove principles; they're yours,
     visible, and sealed at rest.
  2. **It frames, never decides.** Vera lays a choice against your principles and
     shows how they pull — "by your own 'experience over easy comfort', you'd
     lean toward X." The decision is always yours.

A few classic decision lenses ship as *offered* starting points (not assumed
truths) you can adopt or ignore.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from . import security

_FILE = "principles.json"


# Offered starting lenses — NOT assumed to be yours. `preview_lenses()` shows
# them; you adopt the ones that fit with `add()`.
_SUGGESTED = [
    ("need before want", "When they conflict, a real need outranks a want."),
    ("experience over easy happiness", "Favour what makes a life worth remembering over momentary comfort."),
    ("reversible over fast", "Prefer the option you can undo; slow down where a step can't be taken back."),
    ("build over describe", "A working thing beats a plan about the thing."),
    ("presence over optimization", "Some moments (family, rest) aren't to be optimized — protect them."),
]


@dataclass
class Principle:
    text: str            # the principle, in your words ("experience over easy happiness")
    why: str = ""        # your reason, optional
    weight: int = 1      # how strongly it pulls (1..3)
    added: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "why": self.why, "weight": self.weight, "added": self.added}


def _load() -> list[Principle]:
    raw = security.read_state(security.path(_FILE), default=[])
    out = []
    for r in raw if isinstance(raw, list) else []:
        if isinstance(r, dict) and r.get("text"):
            out.append(Principle(text=r["text"], why=r.get("why", ""),
                                 weight=int(r.get("weight", 1)), added=float(r.get("added", 0))))
    return out


def _save(items: list[Principle]) -> None:
    security.write_state(security.path(_FILE), [p.to_dict() for p in items])


# ── manage your principles ─────────────────────────────────────────────────────
def add(text: str, why: str = "", weight: int = 1) -> str:
    text = (text or "").strip()
    if not text:
        return "Tell me the principle in your own words."
    items = _load()
    if any(p.text.lower() == text.lower() for p in items):
        return f"You already hold: '{text}'."
    items.append(Principle(text=text, why=why.strip(), weight=max(1, min(3, weight)), added=time.time()))
    _save(items)
    return f"Added your principle: '{text}'. I'll frame choices through it."


def remove(text: str) -> str:
    items = _load()
    n = len(items)
    items = [p for p in items if p.text.lower() != (text or "").strip().lower()]
    _save(items)
    return f"Removed '{text}'." if len(items) < n else f"You don't hold a principle named '{text}'."


def mine() -> list[Principle]:
    return sorted(_load(), key=lambda p: -p.weight)


def summary() -> str:
    items = mine()
    if not items:
        return ("You haven't told me your decision principles yet. Say things like "
                "'I choose experience over easy comfort' or 'need before want', and "
                "I'll hold them and frame choices through them. (Ask to see suggestions.)")
    lines = ["The principles you decide by:"]
    for p in items:
        star = "★" * p.weight
        lines.append(f"  {star} {p.text}" + (f" — {p.why}" if p.why else ""))
    return "\n".join(lines)


def preview_lenses() -> str:
    lines = ["Decision lenses you could adopt (yours to take or leave):"]
    for t, why in _SUGGESTED:
        lines.append(f"  • {t} — {why}")
    lines.append("\nTell me which fit ('adopt need before want') and I'll hold them as yours.")
    return "\n".join(lines)


# ── frame a choice through your principles (frames, never decides) ─────────────
def frame(choice: str) -> str:
    """Lay a decision against the principles you hold, and show how they pull.
    Never returns 'do X' — it returns how YOUR OWN principles bear on it."""
    choice = (choice or "").strip()
    if not choice:
        return "Tell me the choice you're weighing."
    items = mine()
    if not items:
        return ("I don't yet know the principles you decide by — tell me a few "
                "('experience over easy comfort', 'need before want') and I'll "
                "weigh choices the way you actually think.")
    lines = [f"Weighing: {choice}", "", "Through your own principles:"]
    for p in items:
        star = "★" * p.weight
        lines.append(f"  {star} {p.text}" + (f" ({p.why})" if p.why else ""))
    lines.append("")
    lines.append("These are the lenses you told me you decide by — I'm holding the "
                 "choice up to them, not choosing for you. Which one pulls hardest here?")
    return "\n".join(lines)
