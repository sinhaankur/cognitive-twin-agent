"""
room — Vera reads the room and adapts how she speaks.

Before saying anything, Vera checks the situation and shapes her VOICE to it —
the way a thoughtful person reads a room: louder in a meeting so she's heard,
quieter late at night, softer when you're angry, brighter when you're exploring.
All signals are on-device (frontmost app, ambient loudness, Focus/DND, time,
mood) — no audio or frames are stored.

It returns a VoicePolicy the TTS layer consults:
  * volume   0..100  (maps to macOS `say [[volm ...]]`)
  * rate     words/min
  * mode     "voice" | "text"      (discreet mode → text, never speaks over you)
  * reason   a short human string ("in a meeting — speaking up")

Meeting rule (Ankur's choice): in a meeting Vera speaks LOUDER so the room hears
her, scaling with how noisy it is. Discreet mode is the opposite escape hatch
for shared-screen / Do-Not-Disturb moments.
"""

from __future__ import annotations

import datetime as _dt
import os
from dataclasses import dataclass


# Apps that mean "you're in a call / meeting" (frontmost or running).
_MEETING_APPS = (
    "zoom", "zoom.us", "microsoft teams", "teams", "google meet", "meet",
    "facetime", "webex", "cisco webex", "skype", "slack",  # slack huddles
    "discord", "whereby", "gotomeeting", "bluejeans",
)


@dataclass
class VoicePolicy:
    volume: int           # 0..100
    rate: int             # words per minute
    mode: str             # "voice" | "text"
    reason: str           # why (shown/logged, builds trust)
    tone: str = "warm"    # a hint for phrasing ("gentle" | "warm" | "bright")


def _now_hour() -> int:
    return _dt.datetime.now().hour


def _frontmost_app() -> str:
    try:
        from . import control
        raw = control.current_app()  # "Frontmost app: X" or "[...]"
        if raw.startswith("["):
            return ""
        return raw.split(":", 1)[-1].strip().lower()
    except Exception:
        return ""


def in_meeting() -> bool:
    """Best-effort: is a meeting/call happening? Frontmost meeting app is the
    strong signal; env CTWIN_IN_MEETING=1 forces it (e.g. a Shortcut sets it)."""
    if os.environ.get("CTWIN_IN_MEETING", "").strip() in {"1", "true", "yes", "on"}:
        return True
    app = _frontmost_app()
    return any(m in app for m in _MEETING_APPS)


def _ambient_loud() -> float:
    """Room loudness 0..1 if presence is active, else 0.0 (unknown = quiet)."""
    try:
        from . import presence
        amb = presence.ambient_current()
        return float(amb["loud"]) if amb and "loud" in amb else 0.0
    except Exception:
        return 0.0


def _focus_or_dnd() -> bool:
    """macOS Focus / Do Not Disturb on? Read the assertion flags (best-effort)."""
    try:
        import subprocess
        out = subprocess.run(
            ["defaults", "-currentHost", "read",
             "com.apple.controlcenter", "FocusModes"],
            capture_output=True, text=True, timeout=3)
        # if the key exists and mentions an active mode, treat as DND
        return "1" in (out.stdout or "") and out.returncode == 0
    except Exception:
        return False


def _mood_word() -> str:
    """A coarse mood read (anger / work / exploration / calm) from mood.py."""
    try:
        from . import mood
        p = (mood.mood_prompt() or "").lower()
        for w in ("anger", "angry", "frustrat", "upset"):
            if w in p:
                return "anger"
        for w in ("explor", "curious", "playful", "excit"):
            if w in p:
                return "exploration"
        for w in ("work", "focus", "busy", "deadline"):
            if w in p:
                return "work"
    except Exception:
        pass
    return "calm"


def discreet() -> bool:
    """Discreet mode: Vera renders text, never speaks aloud. On when Focus/DND is
    engaged or forced via env CTWIN_DISCREET=1 (toggle / shared-screen)."""
    if os.environ.get("CTWIN_DISCREET", "").strip() in {"1", "true", "yes", "on"}:
        return True
    return _focus_or_dnd()


def read_room() -> VoicePolicy:
    """Fuse the signals into one voice policy. This is the 'read the room' brain."""
    # Discreet wins over everything — never talk over a shared screen / DND.
    if discreet():
        return VoicePolicy(volume=0, rate=168, mode="text",
                            reason="discreet mode — showing text, not speaking",
                            tone="gentle")

    loud = _ambient_loud()           # 0..1
    hour = _now_hour()
    mood = _mood_word()

    # base: a warm, intimate default
    volume, rate, tone = 72, 168, "warm"

    # MEETING → speak up (Ankur's rule): louder, a touch faster, audible to room.
    if in_meeting():
        volume = 95
        rate = 176
        tone = "bright"
        reason = "in a meeting — speaking up so the room hears"
        # even louder if the room itself is noisy
        if loud >= 0.4:
            volume = 100
            reason = "in a loud meeting — at full volume"
        return VoicePolicy(volume, rate, "voice", reason, tone)

    # not in a meeting: scale gently with ambient noise so she's always audible
    volume = int(min(90, 60 + loud * 45))   # quiet room ~60 → loud ~90

    # late night → quieter + gentler
    if hour >= 23 or hour < 7:
        volume = min(volume, 55)
        rate = 158
        tone = "gentle"
        return VoicePolicy(volume, rate, "voice", "it's late — keeping it soft", tone)

    # mood adaptation (your mood swings): soften for anger, brighten for exploration
    if mood == "anger":
        volume = min(volume, 62)
        rate = 156
        tone = "gentle"
        reason = "you seem tense — softer and slower"
    elif mood == "exploration":
        rate = 174
        tone = "bright"
        reason = "you're in an exploring mood — brighter"
    elif mood == "work":
        rate = 172
        tone = "warm"
        reason = "you're in work mode — clear and efficient"
    else:
        reason = "relaxed — a warm, natural voice"

    return VoicePolicy(volume, rate, "voice", reason, tone)
