"""
Tests for local speech-to-text — the Apple-Speech BYPASS.

The macOS app captures mic audio itself and POSTs a WAV to POST /api/transcribe,
which runs the on-device Whisper (faster-whisper). These tests cover the pure
logic around it (model selection, graceful degrade) WITHOUT needing a Whisper
model installed — so they're fast and run anywhere.

Run: python tests/test_stt_transcribe.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cognitive_twin.voice import stt


def test_default_model_is_fast_english():
    # base.en is the accuracy/latency sweet spot (tiny.en mis-heard words).
    os.environ.pop("CTWIN_STT_MODEL", None)
    assert stt._default_model() == "base.en"


def test_default_model_env_override():
    os.environ["CTWIN_STT_MODEL"] = "base"
    try:
        assert stt._default_model() == "base"
    finally:
        os.environ.pop("CTWIN_STT_MODEL", None)


def test_warm_never_raises_without_backend(monkeypatch):
    # warm() is best-effort: if no Whisper backend is installed it must stay quiet,
    # never crash the server start.
    monkeypatch.setattr(stt, "_which_backend", lambda: None)
    stt.warm()  # should simply no-op


def test_is_available_reflects_backend(monkeypatch):
    monkeypatch.setattr(stt, "_which_backend", lambda: None)
    assert stt.is_available() is False
    monkeypatch.setattr(stt, "_which_backend", lambda: "faster_whisper")
    assert stt.is_available() is True


def test_transcribe_uses_default_model(monkeypatch):
    # transcribe(None) resolves to the default model and routes through faster-whisper.
    calls = {}

    class _Seg:
        def __init__(self, t):
            self.text = t

    class _Model:
        def transcribe(self, path, **kw):
            calls["path"] = path
            calls["kw"] = kw
            return ([_Seg("hello"), _Seg(" world")], None)

    monkeypatch.setattr(stt, "_load", lambda size: ("faster_whisper", _Model()))
    out = stt.transcribe("/tmp/x.wav")
    assert out == "hello  world".strip() or out == "hello world"
    assert calls["path"] == "/tmp/x.wav"
    # a VAD filter + english hint keep it fast + non-hallucinatory on silence
    assert calls["kw"].get("vad_filter") is True
    assert calls["kw"].get("language") == "en"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
