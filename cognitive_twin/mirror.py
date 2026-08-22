"""
mirror.py — her voice adapts to how YOU speak, but stays her (speech accommodation).

When people talk, each drifts toward the other's speech — pace, energy, brevity,
register, warmth (Communication Accommodation Theory calls it convergence). Vera
does this too: she reads how you speak and leans her delivery + wording toward
you — but only partway. A strong floor (default 30% you / 70% her) keeps her
clearly herself. Your style tints her; it never replaces her. "We keep it."

She learns SLOWLY: a rolling profile of your habitual style, persisted on-device
(honours CTWIN_MEMORY_DIR), private. No model — pure measurement + a bounded lean
that feel.delivery() (voice) and feel.directive() (wording) read.

Mirrors the Human Brain Engine's MirrorEngine so the two stay consistent.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

_FILE = "style_profile.json"
DEFAULT_LEAN = 0.30        # 30% you / 70% her — the identity floor, as a number
LEARN_RATE = 0.15          # slow rolling average — settle on your habits, not one line

_CASUAL = {
    "yeah", "yep", "nah", "lol", "haha", "gonna", "wanna", "kinda", "u", "ur",
    "dude", "bro", "cool", "ok", "okay", "hey", "yo", "sup", "bruh",
    "hai", "nahi", "kya", "accha", "acha", "haan", "beta", "yaar", "matlab",
}
_FORMAL = {
    "therefore", "however", "regarding", "furthermore", "consequently",
    "additionally", "shall", "would", "implementation", "architecture",
    "accordingly", "moreover", "hence", "whom", "specifically",
}
_WARM_WORDS = {"thanks", "thank", "please", "love", "appreciate", "great",
               "awesome", "sorry", "hope", "glad", "happy", "good"}


@dataclass
class SpeechStyle:
    energy: float = 0.5
    brevity: float = 0.5
    formality: float = 0.5
    warmth: float = 0.5


def measure(text: str) -> SpeechStyle:
    """Measure one utterance's style — deterministic, no model."""
    t = (text or "").strip()
    words = re.findall(r"[A-Za-z']+", t)
    n = len(words) or 1
    excl, q = t.count("!"), t.count("?")
    caps = sum(1 for w in words if len(w) > 1 and w.isupper())
    energy = min(1.0, 0.35 + excl * 0.2 + q * 0.05 + (caps / n) * 1.2)
    brevity = max(0.0, min(1.0, 1.0 - (n - 4) / 40))
    lc = {w.lower() for w in words}
    formality = max(0.0, min(1.0, 0.5 + (len(lc & _FORMAL) - len(lc & _CASUAL)) * 0.18))
    warmth = max(0.0, min(1.0, 0.45 + len(lc & _WARM_WORDS) * 0.18 + (excl > 0) * 0.05))
    return SpeechStyle(round(energy, 3), round(brevity, 3),
                       round(formality, 3), round(warmth, 3))


def _path() -> Path:
    d = Path(os.environ.get("CTWIN_MEMORY_DIR", Path.home() / ".cognitive-twin"))
    return d.expanduser() / _FILE


def profile() -> SpeechStyle:
    """The learned rolling profile of how you speak (neutral until learned)."""
    p = _path()
    if p.is_file():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return SpeechStyle(**{k: float(v) for k, v in d.items()
                                  if k in SpeechStyle().__dict__})
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    return SpeechStyle()


def observe(text: str) -> SpeechStyle:
    """Fold this utterance into the rolling profile (slow) + persist. Called once
    per real user turn. Returns the updated profile."""
    now = measure(text)
    p, r = profile(), LEARN_RATE
    p.energy = round(p.energy * (1 - r) + now.energy * r, 3)
    p.brevity = round(p.brevity * (1 - r) + now.brevity * r, 3)
    p.formality = round(p.formality * (1 - r) + now.formality * r, 3)
    p.warmth = round(p.warmth * (1 - r) + now.warmth * r, 3)
    fp = _path()
    try:
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(asdict(p), indent=2), encoding="utf-8")
        os.chmod(fp, 0o600)
    except OSError:
        pass
    return p


def _lean_amount() -> float:
    """How far she leans toward you. Clamped to [0, 0.5] — the floor is hard: at
    most she meets you halfway, and never crosses into copying you."""
    try:
        raw = float(os.environ.get("CTWIN_MIRROR_LEAN", DEFAULT_LEAN))
    except ValueError:
        raw = DEFAULT_LEAN
    return max(0.0, min(0.5, raw))


def lean() -> dict[str, float]:
    """The bounded style-lean (deltas from neutral), for feel.delivery/directive.
    Reads the CURRENT profile; does not learn (observe() does that)."""
    p, amt = profile(), _lean_amount()
    return {
        "energy": round((p.energy - 0.5) * amt * 2, 3),
        "brevity": round((p.brevity - 0.5) * amt * 2, 3),
        "formality": round((p.formality - 0.5) * amt * 2, 3),
        "warmth": round((p.warmth - 0.5) * amt * 2, 3),
        "amount": amt,
    }
