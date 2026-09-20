"""
intents — deterministic command → skill matching, run BEFORE the model.

Why: a local model sometimes ASKS ("which amenity?") instead of CALLING a tool,
even when the request is unambiguous. For clear commands we shouldn't leave that
to the model's judgment at all — we match the intent deterministically and invoke
the skill directly. Reliable "just do it" on a local model.

Rules are intentionally conservative: each needs a strong, unambiguous phrase so
we never hijack a nuanced ask. Anything not matched falls through to the model as
before. The matched skill still goes through the permission gate (see loop.py) —
this changes WHICH skill runs, never WHETHER it's allowed to.
"""

from __future__ import annotations

import re

# (compiled pattern, skill_name, default_args). Order matters — first match wins.
# Keep phrases specific: a bare verb ("book") shouldn't fire; "book an amenity"
# should. The skill itself supplies sensible defaults (e.g. amenity picks a slot).
_RULES: list[tuple[re.Pattern, str, dict]] = [
    (re.compile(r"\bbook (an? )?amenit", re.I), "book_amenity", {}),
    (re.compile(r"\b(check|any) .*amenit|amenit.*(availab|open|free)", re.I),
     "check_amenity_availability", {}),
    (re.compile(r"\b(what('?s| is) on )?my day\b|\bmy schedule today\b", re.I), "my_day", {}),
    (re.compile(r"\bwhat am i (building|working on)\b|\bmy projects\b", re.I), "list_projects", {}),
    (re.compile(r"\bgood (morning|evening|afternoon)\b|\bgreet me\b", re.I), "greeting", {}),
    (re.compile(r"\bwhat('?s| is) (now )?playing\b|\bnow playing\b", re.I), "now_playing", {}),
    (re.compile(r"\bwhere (did i go|have i been) today\b", re.I), "places_today", {}),
]


def match(user_input: str, available: set[str]) -> tuple[str, dict] | None:
    """Return (skill_name, args) if the input clearly maps to an AVAILABLE skill,
    else None. `available` guards against firing a skill that isn't registered."""
    text = (user_input or "").strip()
    if not text or len(text) > 200:  # long, nuanced messages: let the model handle
        return None
    for pat, skill, args in _RULES:
        if skill in available and pat.search(text):
            return skill, dict(args)
    return None
