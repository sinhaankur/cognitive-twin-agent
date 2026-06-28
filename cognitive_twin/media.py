"""
Camera + microphone — opt-in, permissioned, off-by-default.

The twin can *see* you (a webcam still) and *hear* you (a short mic recording) —
but only when you explicitly allow it. This mirrors the safety model of
``control.py`` (screen control): nothing here works unless you turn it on, every
capture is confirmed, and you can revoke at any time.

Safety model:
  1. OFF by default. Each device has its own gate:
       - env:  CTWIN_CAMERA=1 / CTWIN_MIC=1   (per-session)
       - or a persisted consent file you opt into via the CLI/app.
     A device is usable only if its gate is on.
  2. Per-capture confirmation. Every still/recording goes through a confirm hook
     (the CLI prompts y/N; a GUI would show a dialog). Deny = nothing captures.
  3. Local only. Frames/audio are written to a file under the private store and
     never uploaded. There is no network code in this module.
  4. Revocable. ``revoke()`` / ``ctwin media off`` clears consent immediately.

Heavy deps (opencv, sounddevice) are imported lazily, only at capture time, so
the rest of the agent never pays for them and the module imports on any machine.
"""

from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path
from typing import Callable


# ---- private store ------------------------------------------------------------
def _dir() -> Path:
    root = Path(os.environ.get("CTWIN_MEMORY_DIR", Path.home() / ".cognitive-twin"))
    (root / "media").mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, stat.S_IRWXU)
    except OSError:
        pass
    return root


def _media_dir() -> Path:
    return _dir() / "media"


_CONSENT = "media_consent.json"


def _load_consent() -> dict[str, bool]:
    p = _media_dir() / _CONSENT
    try:
        if p.is_file():
            data = json.loads(p.read_text(encoding="utf-8"))
            return {"camera": bool(data.get("camera")), "mic": bool(data.get("mic"))}
    except (OSError, json.JSONDecodeError):
        pass
    return {"camera": False, "mic": False}


def _save_consent(consent: dict[str, bool]) -> None:
    p = _media_dir() / _CONSENT
    existed = p.exists()
    try:
        p.write_text(json.dumps(consent, indent=2), encoding="utf-8")
        if not existed:
            os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass


# ---- opt-in gates (env OR persisted consent) ----------------------------------
def _env_on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def camera_enabled() -> bool:
    return _env_on("CTWIN_CAMERA") or _load_consent()["camera"]


def mic_enabled() -> bool:
    return _env_on("CTWIN_MIC") or _load_consent()["mic"]


def grant(*, camera: bool | None = None, mic: bool | None = None) -> dict[str, bool]:
    """Persist consent for a device (the app/CLI 'allow' action)."""
    c = _load_consent()
    if camera is not None:
        c["camera"] = bool(camera)
    if mic is not None:
        c["mic"] = bool(mic)
    _save_consent(c)
    return c


def revoke() -> dict[str, bool]:
    """Turn both off and wipe persisted consent — the kill switch."""
    c = {"camera": False, "mic": False}
    _save_consent(c)
    return c


# ---- per-capture confirmation hook (default: deny = safe) ---------------------
ConfirmFn = Callable[[str], bool]
_confirm: ConfirmFn = lambda _action: False


def set_confirm(fn: ConfirmFn) -> None:
    global _confirm
    _confirm = fn


# ---- capture (lazy deps, local file out) --------------------------------------
def capture_photo() -> str:
    """Capture one webcam still to a local file. Returns a status string. Off
    unless the camera gate is on AND the capture is confirmed."""
    if not camera_enabled():
        return ("[camera off] The camera is off by default. Enable it for a "
                "session with CTWIN_CAMERA=1, or allow it via `ctwin media on camera`.")
    if not _confirm("Take a photo with the camera now?"):
        return "[cancelled] Did not use the camera."
    try:
        import cv2  # lazy: only needed at capture time
    except ImportError:
        return ("[unavailable] Camera capture needs opencv-python "
                "(`pip install -r requirements-multimodal.txt`).")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        cap.release()
        return "[error] Could not open the camera (is it in use, or permission denied?)."
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return "[error] Camera opened but returned no frame."
    out = _media_dir() / f"photo_{int(time.time())}.jpg"
    try:
        cv2.imwrite(str(out), frame)
        os.chmod(out, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as e:
        return f"[error] Could not save the photo: {e}"
    return f"Saved a photo to {out} (local only)."


def record_audio(seconds: float = 4.0) -> str:
    """Record a short mic clip to a local WAV. Off unless the mic gate is on AND
    the capture is confirmed."""
    if not mic_enabled():
        return ("[mic off] The microphone is off by default. Enable it for a "
                "session with CTWIN_MIC=1, or allow it via `ctwin media on mic`.")
    seconds = max(0.5, min(float(seconds), 30.0))  # clamp — no open-ended recording
    if not _confirm(f"Record {seconds:.0f}s of audio from the microphone now?"):
        return "[cancelled] Did not use the microphone."
    try:
        import sounddevice as sd  # lazy
        import soundfile as sf
    except ImportError:
        return ("[unavailable] Mic capture needs sounddevice + soundfile "
                "(`pip install -r requirements-multimodal.txt`).")
    sample_rate = 16000
    try:
        frames = sd.rec(int(seconds * sample_rate), samplerate=sample_rate,
                        channels=1, dtype="int16")
        sd.wait()
    except Exception as e:  # device/portaudio errors vary; surface clearly
        return f"[error] Recording failed: {e}"
    out = _media_dir() / f"audio_{int(time.time())}.wav"
    try:
        sf.write(str(out), frames, sample_rate)
        os.chmod(out, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as e:
        return f"[error] Could not save the recording: {e}"
    return f"Saved a {seconds:.0f}s recording to {out} (local only)."


# ---- status -------------------------------------------------------------------
def status() -> str:
    cam = "ON" if camera_enabled() else "OFF"
    mic = "ON" if mic_enabled() else "OFF"
    if cam == "OFF" and mic == "OFF":
        return ("media: camera OFF, mic OFF (safe default). Enable per session with "
                "CTWIN_CAMERA=1 / CTWIN_MIC=1, or persist with `ctwin media on camera|mic`.")
    return (f"media: camera {cam}, mic {mic} — each capture is confirmed; "
            f"files stay local in {_media_dir()}. Revoke with `ctwin media off`.")


if __name__ == "__main__":
    import sys
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "on" and len(sys.argv) > 2:
        dev = sys.argv[2]
        print(grant(camera=True) if dev == "camera" else grant(mic=True) if dev == "mic"
              else "usage: media on camera|mic")
    elif arg == "off":
        print("revoked:", revoke())
    else:
        print(status())
