"""
In-chat "remember this about me" — teach Vera mid-conversation.

A clear "remember / note / don't forget X" seals the fact to her persona and she
confirms; "forget X" drops it. Reminiscing ("remember when…", "do you remember…")
and questions are NOT commands and pass through to the normal reply. Facts are
sealed on-device and surface in the prompt so they actually shape her replies.
"""
from __future__ import annotations

import tempfile

from cognitive_twin import persona


def _fresh(monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())


def test_remember_stores_and_confirms(monkeypatch):
    _fresh(monkeypatch)
    ack = persona.handle_memory_command("remember my sister is Riya")
    assert ack and "remember" in ack.lower()
    assert "my sister is Riya" in persona.load().remembered


def test_remembered_fact_enters_the_prompt(monkeypatch):
    _fresh(monkeypatch)
    persona.handle_memory_command("remember I am lactose intolerant")
    pr = persona.to_prompt()
    assert "lactose intolerant" in pr


def test_forget_removes(monkeypatch):
    _fresh(monkeypatch)
    persona.handle_memory_command("remember I love hiking")
    persona.handle_memory_command("forget hiking")
    assert not any("hiking" in r for r in persona.load().remembered)


def test_reminiscing_is_not_a_command(monkeypatch):
    _fresh(monkeypatch)
    before = list(persona.load().remembered)
    for t in ["remember when we went to the beach?",
              "do you remember my birthday",
              "remember how fun that was"]:
        assert persona.handle_memory_command(t) is None
    # nothing new was stored from the reminiscing turns
    assert persona.load().remembered == before


def test_plain_turn_passes_through(monkeypatch):
    _fresh(monkeypatch)
    assert persona.handle_memory_command("what should I cook tonight") is None


def test_dedupe(monkeypatch):
    _fresh(monkeypatch)
    persona.handle_memory_command("remember I am vegetarian")
    persona.handle_memory_command("remember I am vegetarian")
    assert persona.load().remembered.count("I am vegetarian") == 1


def test_remembered_is_sealed(monkeypatch, tmp_path):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", str(tmp_path))
    persona.handle_memory_command("remember my passcode hint is the usual")
    f = tmp_path / "persona.json"
    if f.exists():
        raw = f.read_bytes()
        assert not raw.lstrip().startswith(b"{")   # sealed, not plaintext
