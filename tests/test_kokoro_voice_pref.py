"""Her chosen Kokoro voice must SURVIVE a restart.

The picker used to set only an in-process env var, so the choice evaporated on
the next service restart and she fell back to af_heart — "the app still doesn't
have the voice I selected." These tests pin the fix: set_voice persists to disk,
_voice() reads it back in a fresh process state, and an explicit env override
still wins.
"""

from __future__ import annotations

from cognitive_twin.voice import kokoro_tts as k


def test_set_voice_persists_across_restart(tmp_path, monkeypatch):
    # isolated memory dir so we never touch the real pref
    monkeypatch.setenv("CTWIN_MEMORY_DIR", str(tmp_path))
    monkeypatch.delenv("CTWIN_KOKORO_VOICE", raising=False)

    assert k.set_voice("af_bella") is True
    assert k._pref_path().exists()

    # simulate a restart: the env var set by set_voice is gone, only disk remains
    monkeypatch.delenv("CTWIN_KOKORO_VOICE", raising=False)
    assert k._saved_voice() == "af_bella"
    assert k._voice() == "af_bella"


def test_env_override_beats_saved(tmp_path, monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", str(tmp_path))
    monkeypatch.delenv("CTWIN_KOKORO_VOICE", raising=False)
    k.set_voice("af_bella")                       # saved on disk
    monkeypatch.setenv("CTWIN_KOKORO_VOICE", "af_sky")
    assert k._voice() == "af_sky"                 # explicit env wins


def test_bad_voice_rejected_and_pref_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", str(tmp_path))
    monkeypatch.delenv("CTWIN_KOKORO_VOICE", raising=False)
    k.set_voice("af_bella")
    assert k.set_voice("not_a_real_voice") is False
    assert k._voice() == "af_bella"               # unchanged


def test_default_when_nothing_chosen(tmp_path, monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", str(tmp_path))
    monkeypatch.delenv("CTWIN_KOKORO_VOICE", raising=False)
    # no pref written, no env → the shipped default
    assert k._saved_voice() is None
    assert k._voice() == k._DEFAULT_VOICE
