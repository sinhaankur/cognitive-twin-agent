"""
pronounce — Vera learns YOUR words (names, Hindi/English terms) so she stops
mishearing them. A sealed personal lexicon that biases the recogniser, grows from
your corrections + accepted turns, and is empty-safe (changes nothing until used).
"""
from __future__ import annotations

import tempfile

from cognitive_twin import pronounce


def _fresh(monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())


def test_empty_is_safe(monkeypatch):
    _fresh(monkeypatch)
    assert pronounce.is_active() is False
    assert pronounce.prompt() == ""              # no hint → changes nothing


def test_add_and_prompt(monkeypatch):
    _fresh(monkeypatch)
    pronounce.add("Vera", "Shweta", "karo")
    assert pronounce.is_active() is True
    p = pronounce.prompt()
    assert "Vera" in p and "Shweta" in p and "karo" in p
    # the frame tells Whisper to expect English + Hindi
    assert "Hindi" in p


def test_correction_is_learned_weighted(monkeypatch):
    _fresh(monkeypatch)
    pronounce.learn_correction(misheard="Tevira", correct="Vera here")
    p = pronounce.prompt()
    assert "Vera" in p
    # the misheard token is NOT added as a word
    assert "Tevira" not in p


def test_accepted_turn_reinforces_rare_words(monkeypatch):
    _fresh(monkeypatch)
    pronounce.note_accepted("remind Shweta about the Ranchi property")
    p = pronounce.prompt()
    assert "Shweta" in p and "Ranchi" in p
    # common filler words are NOT biased toward
    assert "about" not in p.split("they use: ")[-1]


def test_cap_keeps_most_weighted(monkeypatch):
    _fresh(monkeypatch)
    # flood with many words, then bump one — it must survive the cap
    for i in range(300):
        pronounce.add(f"word{i}")
    pronounce.add("Vera", weight=50)
    assert len(pronounce._terms()) <= pronounce._MAX_TERMS
    assert "Vera" in pronounce.prompt()


def test_forget_and_clear(monkeypatch):
    _fresh(monkeypatch)
    pronounce.add("Vera", "Ankur")
    pronounce.forget("Ankur")
    assert "Ankur" not in pronounce._terms()
    pronounce.clear()
    assert pronounce.is_active() is False


def test_sealed_on_disk(monkeypatch, tmp_path):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", str(tmp_path))
    pronounce.add("Vera")
    f = tmp_path / "pronounce.json"
    if f.exists():
        assert not f.read_bytes().lstrip().startswith(b"{")   # sealed, not plaintext
