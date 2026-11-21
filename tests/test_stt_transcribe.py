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


def test_default_model_is_accurate_english():
    # small.en: understands you through background music + catches short phrases
    # that base.en/tiny.en dropped. Override via CTWIN_STT_MODEL for speed.
    os.environ.pop("CTWIN_STT_MODEL", None)
    assert stt._default_model() == "small.en"


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
    # noise-robustness: a real beam search + no cross-chunk conditioning (stops
    # hallucination/looping under background music)
    assert calls["kw"].get("beam_size", 1) >= 2
    assert calls["kw"].get("condition_on_previous_text") is False


def test_detail_flags_music_when_no_speech(monkeypatch):
    # VAD found NO speech → music_like True (background, not you talking to her).
    class _Model:
        def transcribe(self, path, **kw):
            return (iter([]), None)   # no segments

    monkeypatch.setattr(stt, "_load", lambda size: ("faster_whisper", _Model()))
    d = stt.transcribe_detail("/tmp/x.wav")
    assert d["music_like"] is True
    assert d["text"] == ""


def test_detail_passes_clear_speech(monkeypatch):
    class _Seg:
        def __init__(self, t, nsp, alp):
            self.text, self.no_speech_prob, self.avg_logprob = t, nsp, alp

    class _Model:
        def transcribe(self, path, **kw):
            return (iter([_Seg("come here please", 0.05, -0.3)]), None)

    monkeypatch.setattr(stt, "_load", lambda size: ("faster_whisper", _Model()))
    d = stt.transcribe_detail("/tmp/x.wav")
    assert d["music_like"] is False          # confident speech → not background
    assert "come here" in d["text"]


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
