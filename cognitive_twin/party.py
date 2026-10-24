"""
party — Vera's laser-light "party mode" (the BTK10 sound-reactive BT laser).

The BTK10 is a Bluetooth *sound-reactive* laser: it pairs as an audio sink
(A2DP) so it can "hear" whatever the Mac plays and pulse/move its beams to the
beat. "Party mode" = point the Mac's audio at the laser (so it reacts), optionally
start music, and — crucially — REMEMBER the previous output device and restore it
when the show ends. No sound silently vanishes into a light forever.

Design, matching Vera's control.py posture (named safe actions, no blind control):
  • OPT-IN — off unless CTWIN_PARTY=1 (or enabled via the setting). Off = inert.
  • Named, reversible actions only: lights_on / lights_off / status. Nothing else.
  • Every action is a local CLI call (blueutil / SwitchAudioSource / osascript) —
    on-device, no network. The security doctor stays SAFE (no egress patterns).
  • lights_off ALWAYS restores the prior audio output, even if music fails.

Requires two tiny local tools (Homebrew): blueutil, switchaudio-osx. If either is
missing, the action explains how to get it rather than failing silently.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import os
import shutil
import subprocess

# The paired laser. Name is what macOS shows; address is the stable identifier.
LASER_NAME = "BTK10"
LASER_ADDR = "05-a3-a8-91-cd-d9"

# Where we stash the output device to restore when the show ends (sealed, on-device).
_PREV_OUTPUT_KEY = "party_prev_output.txt"


# ── opt-in gate ────────────────────────────────────────────────────────────────
def is_enabled() -> bool:
    """Party mode is OFF by default. Turn it on with CTWIN_PARTY=1."""
    return os.environ.get("CTWIN_PARTY", "").strip() in ("1", "true", "yes", "on")


def enable(on: bool = True) -> None:
    os.environ["CTWIN_PARTY"] = "1" if on else "0"


# ── tiny local-tool helpers ─────────────────────────────────────────────────────
def _tool(name: str) -> str | None:
    return shutil.which(name)


def _run(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or p.stderr or "").strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def _missing_tools() -> list[str]:
    return [t for t in ("blueutil", "SwitchAudioSource") if not _tool(t)]


def _current_output() -> str:
    _, out = _run(["SwitchAudioSource", "-c"])
    return out


def _set_output(device: str) -> bool:
    code, _ = _run(["SwitchAudioSource", "-s", device, "-t", "output"])
    return code == 0


def _laser_connected() -> bool:
    code, out = _run(["blueutil", "--is-connected", LASER_ADDR])
    return code == 0 and out.strip() == "1"


def _connect_laser() -> bool:
    if _laser_connected():
        return True
    _run(["blueutil", "--connect", LASER_ADDR], timeout=12.0)
    return _laser_connected()


# ── sealed note of the output to restore ────────────────────────────────────────
def _save_prev(device: str) -> None:
    try:
        from . import security
        security.write_state(security.path(_PREV_OUTPUT_KEY), {"device": device})
    except Exception:
        pass


def _load_prev() -> str | None:
    try:
        from . import security
        data = security.read_state(security.path(_PREV_OUTPUT_KEY), default=None)
        if isinstance(data, dict):
            return data.get("device") or None
    except Exception:
        pass
    return None


# ── music (optional; reuse the app's own player path, no new egress) ────────────
def _play_music() -> str:
    """Start Apple Music playing so the laser has a beat to react to. Uses local
    AppleScript only — no streaming service is contacted by us."""
    script = 'tell application "Music" to play'
    code, _ = _run(["osascript", "-e", script], timeout=8.0)
    return "music started" if code == 0 else "couldn't start Music (start a track yourself)"


def _pause_music() -> None:
    _run(["osascript", "-e", 'tell application "Music" to pause'], timeout=6.0)


# ── the named safe actions ───────────────────────────────────────────────────────
def lights_on(music: bool = True) -> str:
    """Begin the laser show: connect BTK10, route Mac audio to it (so it reacts),
    and optionally start music. Remembers the current output to restore later."""
    if not is_enabled():
        return ("Party mode is off (opt-in). Turn it on first — set CTWIN_PARTY=1 "
                "or enable it in Vera's settings.")
    missing = _missing_tools()
    if missing:
        return ("I need these local tools first (Homebrew): "
                + ", ".join(missing) + ".  Install with:  brew install "
                + " ".join("switchaudio-osx" if m == "SwitchAudioSource" else m for m in missing))

    if not _connect_laser():
        return (f"Couldn't reach the {LASER_NAME} laser over Bluetooth. Is it powered "
                "on and in range? (It stays paired; just needs to be awake.)")

    prev = _current_output()
    if prev and prev != LASER_NAME:
        _save_prev(prev)             # so lights_off can put sound back
    if not _set_output(LASER_NAME):
        return f"Connected the laser, but couldn't route audio to it. Try again?"

    note = _play_music() if music else "no music (you control playback)"
    return (f"Lights on — audio is going to the {LASER_NAME}, so the beams react to the "
            f"sound; {note}. Say 'lights off' when you're done and I'll put your sound back.")


def lights_off() -> str:
    """End the show: restore the previous audio output (your speakers) and pause
    music. Always safe to call — if nothing was on, it just confirms."""
    if _missing_tools():
        return "The audio tools aren't installed, so there's nothing routed to restore."
    prev = _load_prev() or "MacBook Pro Speakers"
    _pause_music()
    restored = _set_output(prev)
    where = prev if restored else "your speakers (please pick the output manually)"
    return f"Lights off — your sound is back on {where}. The laser stays paired for next time."


def status() -> str:
    """Where things stand: opt-in state, laser connection, and current audio output."""
    bits = [f"Party mode: {'on' if is_enabled() else 'off (opt-in)'}"]
    if _missing_tools():
        bits.append("tools missing: " + ", ".join(_missing_tools()))
    else:
        bits.append(f"{LASER_NAME}: " + ("connected" if _laser_connected() else "not connected"))
        bits.append("audio output: " + (_current_output() or "unknown"))
    return " · ".join(bits)
