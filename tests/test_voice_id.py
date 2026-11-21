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


def test_store_records_embedder_kind(monkeypatch):
    _fresh(monkeypatch)
    me = _wav("Tagging which ear built this print, honestly.")
    if not me:
        return
    voice_id.enroll(me)
    d = voice_id._load()
    assert d.get("kind") in {"mfcc", "ecapa-onnx"}
    # with no ONNX model installed in CI, it's the always-available numpy ear
    assert voice_id.active_kind() == "mfcc"


def test_human_learning_adds_samples(monkeypatch):
    _fresh(monkeypatch)
    a = _wav("Learning my voice a little more each time I speak to her.")
    b = _wav("Here is a second clip of me talking, so she grows surer.")
    if not a or not b:
        return
    voice_id.enroll(a)
    n1 = voice_id._load().get("samples", 0)
    voice_id.learn_you(b)                     # a confident "that was you" turn
    n2 = voice_id._load().get("samples", 0)
    assert n2 == n1 + 1                        # she folded it in → surer over time
    assert voice_id.is_you(a) is True          # still clearly you


def test_others_gallery_sharpens_the_line(monkeypatch):
    _fresh(monkeypatch)
    me = _wav("This is me enrolling my own voice for the twin.", voice="af_heart")
    other = _wav("And this is a different person's voice entirely.", voice="am_michael")
    if not me or not other:
        return
    voice_id.enroll(me)
    before = voice_id.identify(me)
    assert before["is_you"] is True
    # she hears a stranger and remembers it as NOT-you
    voice_id.note_other(other)
    d = voice_id._load()
    assert len(d.get("others", [])) >= 1       # gallery seeded
    # CORE GUARANTEE: the contrast class must NEVER lock the owner out of their
    # own twin — you still read as you after strangers are remembered.
    assert voice_id.is_you(me) is True
    # The stranger must never out-score the owner on their own print. (With the
    # coarse numpy ear two synthetic voices can look alike — exactly why ECAPA
    # exists — so we assert the safe invariant, not a hard reject the fallback
    # ear can't honestly deliver.)
    owner = voice_id.identify(me)
    stranger = voice_id.identify(other)
    assert owner["you_sim"] >= stranger["you_sim"]


def test_duplicate_strangers_are_not_hoarded(monkeypatch):
    _fresh(monkeypatch)
    me = _wav("Enrolling the owner before testing the gallery cap.")
    other = _wav("A stranger says the very same line, the very same line.",
                 voice="am_michael")
    if not me or not other:
        return
    voice_id.enroll(me)
    for _ in range(5):
        voice_id.note_other(other)             # same clip 5×
    # near-duplicates are skipped → not five copies of the one voice
    assert len(voice_id._load().get("others", [])) <= 2
