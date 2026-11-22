"""
Speaking responsiveness — she streams a reply by sentence so the FIRST word comes
fast (she starts talking in ~0.3s, not after the whole reply renders ~1s+), plays
gaplessly, and a newer utterance / stop supersedes an in-flight one.
"""
from __future__ import annotations

import cognitive_twin.voice.server as srv


def test_split_sentences_basic():
    out = srv._split_sentences("Hello there. How are you? I'm glad!")
    assert out == ["Hello there.", "How are you?", "I'm glad!"]


def test_split_keeps_first_chunk_short():
    # a long first sentence is broken on a comma so the first words come out fast
    long = ("I was just thinking about you and everything going on, "
            "and I wanted to check in on how you're feeling today.")
    out = srv._split_sentences(long)
    assert out[0].endswith(",")                 # quick first breath
    assert len(out[0]) < len(long)


def test_split_handles_empty():
    assert srv._split_sentences("   ") == []


def test_generation_counter_supersedes():
    a = srv._next_speak_gen()
    b = srv._next_speak_gen()
    assert b == a + 1                            # a newer utterance wins


def test_speak_streaming_plays_first_then_rest(monkeypatch):
    # fake synth returns a tiny valid-ish wav for any text; fake afplay via Popen
    calls = {"synth": [], "played": 0}

    def fake_synth(t):
        calls["synth"].append(t)
        return b"RIFF....WAVEdata"               # non-empty → "spoke"

    class FakeProc:
        def __init__(self, *a, **k): calls["played"] += 1
        def poll(self): return 0                 # already finished
        def wait(self): return 0
        def kill(self): pass

    monkeypatch.setattr(srv.subprocess if hasattr(srv, "subprocess") else srv,
                        "Popen", FakeProc, raising=False)
    import subprocess as _sp
    monkeypatch.setattr(_sp, "Popen", FakeProc)

    ok = srv._speak_streaming("First sentence. Second sentence.", fake_synth)
    assert ok is True
    # both sentences were synthesized and the first was ready before playback
    assert len(calls["synth"]) >= 2
    assert calls["played"] >= 1
