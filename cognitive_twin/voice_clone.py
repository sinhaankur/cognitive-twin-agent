"""
Voice clone — let Anita speak in a loved one's *actual* voice, locally.

This stores a reference voice sample (e.g. your mother's recording) on your
machine and, when a local cloning engine is installed, renders Anita's replies in
that voice. It NEVER uploads the sample — cloning runs on-device.

Engines, in preference order (auto-detected):
  - XTTS-v2 (Coqui TTS)  — clones from a ~6s sample; best quality.
  - F5-TTS               — alternative local cloner.
If none is installed, `is_ready()` is False and the app keeps using the warm
built-in voice — so nothing breaks; the real voice turns on once an engine is set
up (see scripts/setup-voice-clone.sh).

Design note: this module is intentionally small and dependency-free at import.
The heavy ML libs are imported lazily, only when actually synthesizing, so the
rest of the agent never pays for them.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any


def _dir() -> Path:
    root = Path(os.environ.get("CTWIN_MEMORY_DIR", Path.home() / ".cognitive-twin"))
    (root / "voice").mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, stat.S_IRWXU)
    except OSError:
        pass
    return root


def _voice_dir() -> Path:
    return _dir() / "voice"


SAMPLE = "reference.wav"        # the loved one's voice sample
META = "voice_clone.json"
OUT = "anita_say.wav"           # last rendered line


# --- managing the reference sample --------------------------------------------
def set_reference(path: str, *, person: str = "") -> dict[str, Any]:
    """Copy a voice sample into Anita's private store. Returns status. The file
    is kept on-device, owner-only. WAV/MP3/M4A accepted; converted to wav if
    ffmpeg is available."""
    src = Path(path).expanduser()
    if not src.is_file():
        return {"ok": False, "error": f"file not found: {path}"}

    dst = _voice_dir() / SAMPLE
    try:
        if src.suffix.lower() == ".wav":
            shutil.copy2(src, dst)
        elif shutil.which("ffmpeg"):
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(src), "-ar", "22050", "-ac", "1", str(dst)],
                capture_output=True, timeout=120, check=False)
        else:
            # no ffmpeg: keep the original extension, store as-is
            dst = _voice_dir() / ("reference" + src.suffix.lower())
            shutil.copy2(src, dst)
        os.chmod(dst, stat.S_IRUSR | stat.S_IWUSR)
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "error": str(e)}

    meta = {"person": person, "sample": dst.name, "engine": detect_engine()}
    _write_meta(meta)
    return {"ok": True, **meta, "ready": is_ready()}


def reference_path() -> Path | None:
    for name in (SAMPLE, "reference.mp3", "reference.m4a"):
        p = _voice_dir() / name
        if p.is_file():
            return p
    return None


def has_reference() -> bool:
    return reference_path() is not None


# --- engine detection ---------------------------------------------------------
def detect_engine() -> str | None:
    """Which local cloning engine is available, if any. Checks a dedicated venv
    first (CTWIN_TTS_PYTHON), then the current interpreter."""
    py = _engine_python()
    if py is None:
        return None
    for mod, name in (("TTS", "xtts"), ("f5_tts", "f5")):
        try:
            r = subprocess.run([py, "-c", f"import {mod}"], capture_output=True, timeout=20)
            if r.returncode == 0:
                return name
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def _engine_python() -> str | None:
    """The Python that has the cloning libs. A separate env is normal because the
    libs need Python 3.9–3.11. Set CTWIN_TTS_PYTHON to point at it."""
    cand = os.environ.get("CTWIN_TTS_PYTHON")
    if cand and Path(cand).exists():
        return cand
    # a conventional location the setup script creates
    venv = Path.home() / ".cognitive-twin" / "tts-venv" / "bin" / "python"
    if venv.exists():
        return str(venv)
    return None


def is_ready() -> bool:
    """True only if we have BOTH a reference sample AND an engine to render it."""
    return has_reference() and detect_engine() is not None


# --- synthesis ----------------------------------------------------------------
def synthesize(text: str) -> Path | None:
    """Render `text` in the cloned voice to a wav file; return its path, or None
    if not ready (caller should fall back to the built-in voice)."""
    if not text.strip() or not is_ready():
        return None
    engine = detect_engine()
    ref = reference_path()
    out = _voice_dir() / OUT
    py = _engine_python()
    if py is None or ref is None:
        return None

    if engine == "xtts":
        # Use the tuned synthesis worker (steadier, warmer clone). Ship the script
        # next to this module so the venv python can run it.
        worker = Path(__file__).resolve().parent / "_xtts_say.py"
        cmd = [py, str(worker), text, str(ref), str(out)]
    else:  # f5
        code = (
            "import sys;from f5_tts.api import F5TTS;"
            "m=F5TTS();m.infer(ref_file=sys.argv[2], ref_text='', gen_text=sys.argv[1], "
            "file_wave=sys.argv[3])"
        )
        cmd = [py, "-c", code, text, str(ref), str(out)]
    try:
        env = dict(os.environ, COQUI_TOS_AGREED="1")
        r = subprocess.run(cmd, capture_output=True, timeout=240, env=env)
        if r.returncode == 0 and out.is_file():
            return out
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def speak(text: str) -> bool:
    """Render in the cloned voice and play it. Returns True if it played; False
    means the caller should fall back to the built-in voice."""
    out = synthesize(text)
    if out is None:
        return False
    player = shutil.which("afplay")  # macOS
    if not player:
        return False
    try:
        subprocess.run([player, str(out)], check=False, timeout=180)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


# --- meta + status ------------------------------------------------------------
def _write_meta(meta: dict[str, Any]) -> None:
    p = _voice_dir() / META
    try:
        p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _meta() -> dict[str, Any]:
    p = _voice_dir() / META
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def clear() -> bool:
    removed = False
    for p in _voice_dir().glob("*"):
        try:
            p.unlink(); removed = True
        except OSError:
            pass
    return removed


def status() -> str:
    if is_ready():
        who = _meta().get("person") or "a loved one"
        return f"voice clone: READY — Anita can speak in {who}'s voice ({detect_engine()}), on-device"
    if has_reference() and detect_engine() is None:
        return ("voice clone: sample saved, but no engine installed yet — "
                "run scripts/setup-voice-clone.sh (uses built-in voice meanwhile)")
    if not has_reference():
        return "voice clone: no voice sample yet"
    return "voice clone: not ready"


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "set":
        print(json.dumps(set_reference(sys.argv[2],
                                       person=sys.argv[3] if len(sys.argv) > 3 else ""), indent=2))
    elif len(sys.argv) > 2 and sys.argv[1] == "say":
        print("played" if speak(sys.argv[2]) else "not ready (no engine/sample) — fall back")
    elif len(sys.argv) > 1 and sys.argv[1] == "clear":
        print("cleared." if clear() else "nothing to clear.")
    else:
        print(status())
