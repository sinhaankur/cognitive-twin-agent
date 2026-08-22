"""
tone.py — YOUR dial on how Vera speaks. An explicit user control, never automatic.

Vera decides her own felt state from what you say (feel.py). But you get the last
word on delivery: this is a small, persistent preference you set — "be blunter",
"warmer", "steadier" — that nudges her stance and voice on every turn. It never
changes on its own; Vera reads it, she doesn't write it (that's the user-action-
only rule — the human holds the dial).

Two axes, each -1..+1, 0 = leave her own read alone:
  bluntness : -1 gentler ………… +1 blunter   (softens/sharpens the posture)
  warmth    : -1 more reserved … +1 warmer    (cools/warms the voice + tone)

Stored locally per-twin (honours CTWIN_MEMORY_DIR), private, on-device.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

_FILE = "tone.json"


@dataclass
class Tone:
    bluntness: float = 0.0
    warmth: float = 0.0

    def clamp(self) -> "Tone":
        self.bluntness = max(-1.0, min(1.0, float(self.bluntness)))
        self.warmth = max(-1.0, min(1.0, float(self.warmth)))
        return self

    @property
    def is_default(self) -> bool:
        return abs(self.bluntness) < 1e-6 and abs(self.warmth) < 1e-6


def _dir() -> Path:
    return Path(os.environ.get("CTWIN_MEMORY_DIR",
                               Path.home() / ".cognitive-twin")).expanduser()


def _path() -> Path:
    return _dir() / _FILE


def get() -> Tone:
    """The current dial. Defaults to neutral (Vera's own read) if never set.
    Read through the security kernel — the dial is personal state, so it lives
    SEALED on disk (encrypted, owner-only), never plaintext."""
    try:
        from . import security
        data = security.read_state(_path(), default=None)
    except Exception:
        data = None
    if isinstance(data, dict):
        try:
            return Tone(bluntness=data.get("bluntness", 0.0),
                        warmth=data.get("warmth", 0.0)).clamp()
        except (TypeError, ValueError):
            pass
    return Tone()


def set(*, bluntness: float | None = None, warmth: float | None = None) -> Tone:
    """Set the dial (explicit user action). Only the axes you pass change.
    Persisted via the security kernel (sealed, atomic, owner-only)."""
    t = get()
    if bluntness is not None:
        t.bluntness = float(bluntness)
    if warmth is not None:
        t.warmth = float(warmth)
    t.clamp()
    try:
        from . import security
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        security.write_state(p, asdict(t))    # sealed — the only way state hits disk
    except Exception:
        pass
    return t


def reset() -> Tone:
    """Back to Vera's own read on both axes."""
    return set(bluntness=0.0, warmth=0.0)
