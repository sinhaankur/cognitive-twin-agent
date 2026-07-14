"""
Text-to-speech via macOS `say` — offline, built in, no dependency.

`say` ships with macOS, runs locally, and supports many voices. On non-macOS
systems speak() degrades to a no-op that reports it's unavailable, so callers can
fall back to showing text.
"""

from __future__ import annotations

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


def speak(text: str, *, voice: str | None = None, rate: int | None = None,
          blocking: bool = True) -> bool:
    """Speak `text` aloud. Returns True if speech was dispatched.

    voice    optional `say` voice name (e.g. "Samantha")
    rate     optional words-per-minute (e.g. 180)
    blocking wait for speech to finish (True) or fire-and-forget (False)
    """
    text = (text or "").strip()
    if not text:
        return False
    if not is_available():
        # Honest fallback: no local voice, let the caller show text instead.
        print(f"[tts unavailable] {text}", file=sys.stderr)
        return False

    cmd = ["say"]
    if voice:
        cmd += ["-v", voice]
    if rate:
        cmd += ["-r", str(rate)]
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
