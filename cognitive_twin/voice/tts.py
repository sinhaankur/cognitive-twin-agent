"""
Text-to-speech via macOS `say` — offline, built in, no dependency.

`say` ships with macOS, runs locally, and supports many voices. On non-macOS
systems speak() degrades to a no-op that reports it's unavailable, so callers can
fall back to showing text.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys


def is_available() -> bool:
    """True if the local `say` binary exists (macOS)."""
    return shutil.which("say") is not None


def voices() -> list[str]:
    """List installed `say` voice names (best-effort; empty if unavailable)."""
    if not is_available():
        return []
    try:
        out = subprocess.run(
            ["say", "-v", "?"], capture_output=True, text=True, timeout=5
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    names: list[str] = []
    for line in out.splitlines():
        # format: "Samantha            en_US    # comment"
        parts = line.split()
        if parts:
            names.append(parts[0])
    return names


# Vera's preferred VOICE — a warm, natural female voice that doesn't sound "AI"
# (clear pitch + tone, Her-adjacent). We pick the best one INSTALLED, in order:
# Enhanced/Premium female US voices (most human) → Samantha (the Her namesake) →
# Karen (AU). Override with env CTWIN_VOICE / CTWIN_VOICE_RATE.
_PREFERRED_FEMALE = [
    "Ava (Premium)", "Zoe (Premium)", "Samantha (Enhanced)", "Allison (Enhanced)",
    "Ava (Enhanced)", "Nicky (Enhanced)", "Samantha", "Allison", "Ava", "Nicky",
    "Karen", "Kathy", "Serena", "Moira", "Tessa", "Fiona",
]
_DEFAULT_RATE = 168  # a touch slower than default — warmer, more intimate (Her)
_chosen_voice: str | None = None


def best_voice() -> str | None:
    """The best natural female voice that's actually installed (cached)."""
    global _chosen_voice
    if _chosen_voice is not None:
        return _chosen_voice or None
    env = os.environ.get("CTWIN_VOICE", "").strip()
    installed = set(voices())
    if env and (env in installed or not installed):
        _chosen_voice = env
        return env
    for name in _PREFERRED_FEMALE:
        if name in installed:
            _chosen_voice = name
            return name
    _chosen_voice = ""  # nothing matched; let `say` use the system default
    return None


def speak(text: str, *, voice: str | None = None, rate: int | None = None,
          blocking: bool = True) -> bool:
    """Speak `text` aloud. Returns True if speech was dispatched.

    voice    `say` voice name; defaults to Vera's best installed female voice
    rate     words-per-minute; defaults to a warm, intimate ~168
    blocking wait for speech to finish (True) or fire-and-forget (False)
    """
    text = (text or "").strip()
    if not text:
        return False
    if not is_available():
        # Honest fallback: no local voice, let the caller show text instead.
        print(f"[tts unavailable] {text}", file=sys.stderr)
        return False

    if voice is None:
        voice = best_voice()

    # Read the room: let Vera adapt volume/rate to the situation (meeting → louder,
    # late night → softer, mood swings → gentler/brighter). Discreet mode → don't
    # speak at all (the caller shows text). Honored unless the caller forced a rate
    # or CTWIN_NO_ROOM=1 is set.
    volume = None
    if os.environ.get("CTWIN_NO_ROOM", "").strip() not in {"1", "true", "yes", "on"}:
        try:
            from .. import room
            pol = room.read_room()
            if pol.mode == "text":
                # discreet — stay silent; caller renders text
                return False
            volume = pol.volume
            if rate is None:
                rate = pol.rate
        except Exception:
            pass
    if rate is None:
        try:
            rate = int(os.environ.get("CTWIN_VOICE_RATE", _DEFAULT_RATE))
        except ValueError:
            rate = _DEFAULT_RATE

    cmd = ["say"]
    if voice:
        cmd += ["-v", voice]
    if rate:
        cmd += ["-r", str(rate)]
    # macOS `say` volume via an inline [[volm ...]] command (0.0..1.0).
    if volume is not None:
        text = f"[[volm {max(0.0, min(1.0, volume / 100.0)):.2f}]] {text}"
    cmd.append(text)
    global _proc
    try:
        if blocking:
            _proc = subprocess.Popen(cmd)
            _proc.wait(timeout=120)
        else:
            _proc = subprocess.Popen(cmd)
        return True
    except (OSError, subprocess.SubprocessError) as e:
        print(f"[tts error] {e}", file=sys.stderr)
        return False


# the live `say` process, so barge-in can actually silence her mid-word
_proc: subprocess.Popen | None = None


def stop() -> bool:
    """Stop any in-flight speech immediately (the app's barge-in)."""
    global _proc
    p = _proc
    if p is not None and p.poll() is None:
        try:
            p.terminate()
            return True
        except OSError:
            pass
    return False
