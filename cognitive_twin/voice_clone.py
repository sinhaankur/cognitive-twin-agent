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
        if shutil.which("ffmpeg"):
            # Clean GENTLY for cloning, at XTTS-v2's native 24kHz. We only trim
            # leading/trailing dead air and tame low rumble — we deliberately keep
            # the natural pauses and breathing *between* words, because XTTS clones
            # a real person far more faithfully from continuous speech than from
            # fragments glued together. A light loudnorm evens out the level.
            # (Earlier code downsampled to 22.05k and collapsed every internal
            # pause; both quietly degraded the timbre and rushed the delivery.)
            _filter = (
                "highpass=f=70,"
                "silenceremove=start_periods=1:start_silence=0.15:start_threshold=-45dB,"
                "areverse,"
                "silenceremove=start_periods=1:start_silence=0.15:start_threshold=-45dB,"
                "areverse,"
                "loudnorm=I=-18:TP=-2:LRA=11"
            )
            r = subprocess.run(
                ["ffmpeg", "-y", "-i", str(src), "-af", _filter,
                 "-ar", "24000", "-ac", "1", str(dst)],
                capture_output=True, timeout=180)
            if r.returncode != 0 or not dst.exists():
                # fall back to a plain copy/convert if the filter chain failed
                subprocess.run(["ffmpeg", "-y", "-i", str(src), "-ar", "24000",
                                "-ac", "1", str(dst)], capture_output=True, timeout=120)
        elif src.suffix.lower() == ".wav":
            shutil.copy2(src, dst)
        else:
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


def add_reference(path: str) -> dict[str, Any]:
    """ADD a clip alongside the primary sample. XTTS averages every reference
    into one steadier voice — two or three clean short clips beat one."""
    src = Path(path).expanduser()
    if not src.is_file():
        return {"ok": False, "error": f"file not found: {path}"}
    if reference_path() is None:
        return set_reference(path)          # first clip becomes the primary
    refs = _voice_dir() / "refs"
    refs.mkdir(exist_ok=True)
    n = 1
    while (refs / f"ref-{n}.wav").exists():
        n += 1
    dst = refs / f"ref-{n}.wav"
    try:
        if shutil.which("ffmpeg"):
            subprocess.run(["ffmpeg", "-y", "-i", str(src), "-ar", "24000",
                            "-ac", "1", str(dst)], capture_output=True, timeout=120)
        else:
            shutil.copy2(src, dst)
        os.chmod(dst, stat.S_IRUSR | stat.S_IWUSR)
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "references": len(reference_paths())}


def reference_paths() -> list[Path]:
    """Every reference: the primary sample plus any added clips."""
    out = []
    if (p := reference_path()) is not None:
        out.append(p)
    refs = _voice_dir() / "refs"
    if refs.is_dir():
        out.extend(sorted(refs.glob("ref-*.wav")))
    return out


def has_reference() -> bool:
    return reference_path() is not None


# --- engine detection ---------------------------------------------------------
_SENTINEL = object()       # "engine not checked yet"
_engine_cache: object = _SENTINEL


def detect_engine(refresh: bool = False) -> str | None:
    """Which local cloning engine is available, if any. Cached after the first
    check — the probe spawns a subprocess (import TTS), which is slow (~6s), so we
    only do it once per process unless refresh=True."""
    global _engine_cache
    if not refresh and _engine_cache is not _SENTINEL:
        return _engine_cache  # type: ignore[return-value]
    py = _engine_python()
    result: str | None = None
    if py is not None:
        for mod, name in (("TTS", "xtts"), ("f5_tts", "f5")):
            try:
                r = subprocess.run([py, "-c", f"import {mod}"], capture_output=True, timeout=20)
                if r.returncode == 0:
                    result = name
                    break
            except (OSError, subprocess.SubprocessError):
                pass
    _engine_cache = result
    return result


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
    # every clip counts: XTTS averages all references into a steadier voice
    ref_arg = ",".join(str(p) for p in reference_paths()) or str(ref)

    if engine == "xtts":
        # Use the tuned synthesis worker (steadier, warmer clone). Ship the script
        # next to this module so the venv python can run it.
        worker = Path(__file__).resolve().parent / "_xtts_say.py"
        cmd = [py, str(worker), text, ref_arg, str(out)]
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


# --- persistent warm worker (keeps the model loaded → fast replies) -----------
_worker: subprocess.Popen | None = None


def _ensure_worker():
    """Start (once) a long-lived XTTS process with the model preloaded, so each
    reply renders in ~1-2s instead of a 10-15s cold load. XTTS only."""
    global _worker
    if _worker is not None and _worker.poll() is None:
        return _worker
    if detect_engine() != "xtts":
        return None
    py = _engine_python()
    ref = reference_path()
    if py is None or ref is None:
        return None
    worker_script = Path(__file__).resolve().parent / "_xtts_say.py"
    try:
        env = dict(os.environ, COQUI_TOS_AGREED="1")
        _worker = subprocess.Popen(
            [py, str(worker_script), "--serve",
             ",".join(str(p) for p in reference_paths()) or str(ref)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, env=env)
        # wait for the "ready" line (model loaded)
        line = _worker.stdout.readline()
        if '"ready"' in line:
            return _worker
    except (OSError, subprocess.SubprocessError):
        _worker = None
    return _worker


def synthesize_fast(text: str) -> Path | None:
    """Render via the warm worker if possible; else fall back to one-shot."""
    if not text.strip() or not is_ready():
        return None
    w = _ensure_worker()
    out = _voice_dir() / OUT
    if w is not None and w.poll() is None:
        try:
            w.stdin.write(json.dumps({"text": text, "out": str(out)}) + "\n")
            w.stdin.flush()
            resp = json.loads(w.stdout.readline() or "{}")
            if resp.get("ok") and out.is_file():
                return out
        except (OSError, ValueError):
            pass
    return synthesize(text)  # cold fallback


# barge-in bookkeeping: the live afplay process, plus generation counters so a
# stop that lands while XTTS is still RENDERING silences the playback that
# would have followed (killing nothing isn't the same as staying quiet)
_play_proc: subprocess.Popen | None = None
_speak_gen = 0
_stop_gen = -1


def speak(text: str) -> bool:
    """Render in the cloned voice and play it. Returns True if it played (or
    was deliberately silenced by a barge-in); False means the caller should
    fall back to the built-in voice."""
    global _play_proc, _speak_gen
    _speak_gen += 1
    gen = _speak_gen
    out = synthesize_fast(text)
    if out is None:
        return False
    if _stop_gen >= gen:
        return True      # the user interrupted during render — stay quiet
    player = shutil.which("afplay")  # macOS
    if not player:
        return False
    try:
        _play_proc = subprocess.Popen([player, str(out)])
        _play_proc.wait(timeout=180)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def stop_playback() -> bool:
    """Stop the cloned voice immediately (the app's barge-in) — including a
    voice still in the renderer that hasn't reached the speaker yet."""
    global _play_proc, _stop_gen
    _stop_gen = _speak_gen
    p = _play_proc
    if p is not None and p.poll() is None:
        try:
            p.terminate()
            return True
        except OSError:
            pass
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
    elif len(sys.argv) > 2 and sys.argv[1] == "add":
        # first clip becomes the primary; every further clip steadies the voice
        print(json.dumps(add_reference(sys.argv[2]), indent=2))
    elif len(sys.argv) > 2 and sys.argv[1] == "say":
        print("played" if speak(sys.argv[2]) else "not ready (no engine/sample) — fall back")
    elif len(sys.argv) > 1 and sys.argv[1] == "clear":
        print("cleared." if clear() else "nothing to clear.")
    else:
        print(status())
