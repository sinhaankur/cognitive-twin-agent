"""
Kokoro — Vera's expressive, human-sounding NEURAL voice.

Kokoro-82M (Apache-2.0) is far more natural and EMOTIONAL than a stock system
voice or Piper: real prosody, breath, question-vs-statement intonation. It's what
makes Vera's replies feel like a person, not a readout. Default voice: Bella
(warm, expressive US female).

Architecture (same as the Piper path it supersedes): the brain runs as a
BACKGROUND service that can't PLAY audio but CAN synthesize. A persistent worker
(``kokoro_synth.py`` in VERA_HOME, its own py3.12 venv) keeps the model warm and
turns text → a WAV on /tmp; this module returns the WAV bytes; the app plays them.

Everything is on-device. The venv + worker live under VERA_HOME
(``~/Library/Application Support/Vera``).
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path


def _vera_home() -> Path:
    return Path(os.environ.get("VERA_HOME",
               Path.home() / "Library" / "Application Support" / "Vera"))


def _venv_python() -> Path | None:
    p = _vera_home() / "kokoro-venv" / "bin" / "python3"
    return p if p.is_file() else None


def _worker_script() -> Path | None:
    s = _vera_home() / "kokoro_synth.py"
    return s if s.is_file() else None


# All Kokoro female voices Vera ships, with friendly labels (you asked for the
# full list, selectable). af_ = American female, bf_ = British female.
VOICES: dict[str, str] = {
    "af_bella":   "Bella — warm, expressive US female",
    "af_nicole":  "Nicole — soft, intimate US female",
    "af_sarah":   "Sarah — gentle, clear US female",
    "af_sky":     "Sky — bright, light US female",
    "af_heart":   "Heart — tender US female",
    "af_aoede":   "Aoede — melodic US female",
    "af_kore":    "Kore — steady US female",
    "af_jessica": "Jessica — friendly US female",
    "bf_emma":    "Emma — soft British female",
    "bf_isabella":"Isabella — refined British female",
    "bf_alice":   "Alice — calm British female",
    "bf_lily":    "Lily — light British female",
}

_DEFAULT_VOICE = "af_bella"


def _voice() -> str:
    v = os.environ.get("CTWIN_KOKORO_VOICE", _DEFAULT_VOICE).strip()
    return v if v in VOICES else _DEFAULT_VOICE


def is_available() -> bool:
    return _venv_python() is not None and _worker_script() is not None


def status() -> str:
    if not _venv_python():
        return "kokoro not installed"
    if not _worker_script():
        return "kokoro worker missing"
    return f"kokoro ready ({_voice()})"


def list_voices() -> list[dict[str, str]]:
    """The selectable voices + the current one (for the app's picker)."""
    return [{"id": vid, "label": lbl} for vid, lbl in VOICES.items()]


def current_voice() -> str:
    return _voice()


def set_voice(voice_id: str) -> bool:
    voice_id = (voice_id or "").strip()
    if voice_id in VOICES:
        os.environ["CTWIN_KOKORO_VOICE"] = voice_id
        return True
    return False


# ── the persistent, warm worker ────────────────────────────────────────────────
_proc: subprocess.Popen | None = None
_lock = threading.Lock()


def _ensure_worker() -> subprocess.Popen | None:
    """Start (once) the long-lived Kokoro worker so the model stays warm. Returns
    the process, or None if Kokoro isn't installed / failed to start."""
    global _proc
    if _proc is not None and _proc.poll() is None:
        return _proc
    py, script = _venv_python(), _worker_script()
    if not py or not script:
        return None
    try:
        _proc = subprocess.Popen(
            [str(py), str(script)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            cwd=str(_vera_home()), text=True, bufsize=1,
        )
        # wait for READY (model load can take a few seconds the first time)
        line = _proc.stdout.readline().strip() if _proc.stdout else ""
        if line != "READY":
            # give it one more line in case of a stray warning
            line = _proc.stdout.readline().strip() if _proc.stdout else ""
        return _proc
    except (OSError, ValueError):
        _proc = None
        return None


def synth_wav(text: str, *, speed: float = 0.92) -> bytes | None:
    """Synthesize `text` to WAV bytes with Kokoro. speed < 1 = slower/warmer
    (0.92 reads calm + present, the companion tone). None on any failure, so the
    caller falls back to the system voice."""
    text = " ".join((text or "").split())
    if not text:
        return None
    with _lock:
        proc = _ensure_worker()
        if not proc or not proc.stdin or not proc.stdout:
            return None
        try:
            req = json.dumps({"text": text, "voice": _voice(),
                              "speed": max(0.5, min(1.5, speed))})
            proc.stdin.write(req + "\n")
            proc.stdin.flush()
            resp = proc.stdout.readline().strip()
            data = json.loads(resp)
            wav_path = data.get("wav")
            if not wav_path or not Path(wav_path).is_file():
                return None
            blob = Path(wav_path).read_bytes()
            try:
                os.unlink(wav_path)   # clean up the temp file
            except OSError:
                pass
            return blob if blob[:4] == b"RIFF" else None
        except (OSError, ValueError, json.JSONDecodeError):
            # worker died or returned junk — reset so the next call restarts it
            global _proc
            try:
                if _proc:
                    _proc.kill()
            except OSError:
                pass
            _proc = None
            return None
