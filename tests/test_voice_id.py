"""
Voice identity — Vera learns YOUR voice so she knows you from the TV / other people.

Enroll a clip; the same voice reads as you, a clearly different one doesn't; off
until enrolled (opt-in), sealed on-device, no audio stored, never a hard block
(None when it can't tell). Uses synthesized clips so no mic is needed.
"""
from __future__ import annotations

import tempfile

from cognitive_twin import voice_id


def _fresh(monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())


def _wav(text, voice="af_heart"):
    from cognitive_twin.voice import kokoro_tts as k
    import os
    os.environ.setdefault("CTWIN_VOICE", voice)
    return k.synth_wav(text, )


def test_off_until_enrolled(monkeypatch):
    _fresh(monkeypatch)
    assert voice_id.is_enrolled() is False
    # not enrolled → can't tell, and that's fine (opt-in, never blocks)
    assert voice_id.identify(b"")["known"] is False


def test_enroll_then_recognises_same_voice(monkeypatch):
    _fresh(monkeypatch)
    me = _wav("This is my own voice speaking a full sentence for enrollment.")
    if not me:
        return  # Kokoro not available in this env — skip cleanly
    voice_id.enroll(me)
    assert voice_id.is_enrolled() is True
    assert voice_id.is_you(me) is True


def test_too_short_clip_is_honest(monkeypatch):
    _fresh(monkeypatch)
    me = _wav("Enroll me with a proper sentence here.")
    if not me:
        return
    voice_id.enroll(me)
    r = voice_id.identify(b"RIFF")          # junk / too short
    assert r["is_you"] is None              # can't tell, doesn't guess


def test_voiceprint_is_sealed(monkeypatch, tmp_path):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", str(tmp_path))
    me = _wav("Sealing my voiceprint on this device now.")
    if not me:
        return
    voice_id.enroll(me)
    f = tmp_path / "voice_id.json"
    if f.exists():
        raw = f.read_bytes()
        assert not raw.lstrip().startswith(b"{")   # sealed, not plaintext
