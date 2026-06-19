"""
Speech-to-text via local Whisper — optional, local-first.

Uses faster-whisper if installed (fast, CTranslate2 backend); falls back to
openai-whisper if that's what's present. If neither is installed, is_available()
returns False and the web UI uses the browser's own speech recognition instead —
so the app still works, it just moves transcription into the browser.

    pip install faster-whisper      # recommended
"""

from __future__ import annotations

import sys
from functools import lru_cache
from typing import Any


def _which_backend() -> str | None:
    try:
        import faster_whisper  # noqa: F401
        return "faster_whisper"
    except ImportError:
        pass
    try:
        import whisper  # noqa: F401
        return "openai_whisper"
    except ImportError:
        return None


def is_available() -> bool:
    """True if any local Whisper backend can be imported."""
    return _which_backend() is not None


@lru_cache(maxsize=2)
def _load(model_size: str) -> tuple[str, Any]:
    """Load (and cache) a Whisper model. Returns (backend, model)."""
    backend = _which_backend()
    if backend == "faster_whisper":
        from faster_whisper import WhisperModel
        # int8 on CPU is a good default for a personal machine
        return backend, WhisperModel(model_size, device="auto", compute_type="int8")
    if backend == "openai_whisper":
        import whisper
        return backend, whisper.load_model(model_size)
    raise RuntimeError(
        "No local Whisper backend installed. Run `pip install faster-whisper`."
    )


def transcribe(audio_path: str, *, model_size: str = "base") -> str:
    """Transcribe an audio file to text using local Whisper. Raises if no
    backend is installed (callers should check is_available() first or catch)."""
    backend, model = _load(model_size)
    if backend == "faster_whisper":
        segments, _info = model.transcribe(audio_path, beam_size=1)
        return " ".join(seg.text for seg in segments).strip()
    # openai-whisper
    result = model.transcribe(audio_path)
    return str(result.get("text", "")).strip()


def status() -> str:
    """One-line human status for diagnostics."""
    b = _which_backend()
    if b:
        return f"local STT ready ({b})"
    return "local STT not installed — browser speech will be used (pip install faster-whisper)"


if __name__ == "__main__":
    print(status())
    if len(sys.argv) > 1 and is_available():
        print(transcribe(sys.argv[1]))
