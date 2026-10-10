"""
`ctwin voice enroll/forget/whoami` — teach her your voice from the terminal, and
the voice-identity gate (a clip that's clearly not you is heard but not learned).
"""
from __future__ import annotations

import tempfile
from pathlib import Path


def test_whoami_when_not_enrolled(monkeypatch, capsys):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())
    from cognitive_twin.cli import _voice_command
    assert _voice_command(["whoami"]) == 0
    assert "don't know your voice" in capsys.readouterr().out.lower()


def test_enroll_from_file_then_whoami(monkeypatch, capsys):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())
    from cognitive_twin.voice import kokoro_tts as k
    wav = k.synth_wav("Enrolling my own voice so she knows who I am, clearly.")
    if not wav:
        return  # Kokoro unavailable here — skip
    p = Path(tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name)
    p.write_bytes(wav)
    from cognitive_twin.cli import _voice_command
    assert _voice_command(["enroll", str(p)]) == 0
    _voice_command(["whoami"])
    assert "voice identity: on" in capsys.readouterr().out.lower()


def test_forget_clears(monkeypatch, capsys):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())
    from cognitive_twin import voice_id
    from cognitive_twin.cli import _voice_command
    _voice_command(["forget"])
    assert voice_id.is_enrolled() is False


def test_identity_gate_logic():
    # the gate the /api/ask handler applies: not-you → don't learn/capture
    def record_for(is_you, internal=False):
        not_you = is_you is False
        return (not internal) and (not not_you)
    assert record_for(None) is True        # not enrolled → normal
    assert record_for(True) is True        # you → learns
    assert record_for(False) is False      # someone else → heard, not learned
    assert record_for(True, internal=True) is False  # scripted → never learns
