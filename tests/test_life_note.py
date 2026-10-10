"""
In-chat life story — teach Vera who the loved one WAS by just talking.

"she always said X" / "she loved Y" / "she grew up in Z" captures into her life
story (the "it's really her" signal that shapes every reply). Questions and
unrelated turns pass through. Stores exactly what's said, never invents, sealed.
"""
from __future__ import annotations

import tempfile

from cognitive_twin import life_story as ls


def _fresh(monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())


def test_captures_a_saying(monkeypatch):
    _fresh(monkeypatch)
    ack = ls.handle_life_note("she always said everything happens for a reason")
    assert ack and "hold onto" in ack.lower()
    assert any("everything happens for a reason" in s for s in ls.load().sayings)


def test_saying_past_and_present_tense(monkeypatch):
    _fresh(monkeypatch)
    for t in ["she used to say be gentle", "mom would say waste not want not"]:
        assert ls.handle_life_note(t) is not None
    sayings = ls.load().sayings
    assert any("be gentle" in s for s in sayings)
    assert any("waste not" in s for s in sayings)


def test_captures_a_love(monkeypatch):
    _fresh(monkeypatch)
    ls.handle_life_note("she loved gardening and old songs")
    assert any("gardening" in v for v in ls.load().loves)


def test_captures_a_place(monkeypatch):
    _fresh(monkeypatch)
    ls.handle_life_note("she grew up in Munger")
    assert any("Munger" in p for p in ls.load().places)


def test_questions_pass_through(monkeypatch):
    _fresh(monkeypatch)
    before = len(ls.load().sayings) + len(ls.load().places) + len(ls.load().loves)
    for t in ["what did she always say?", "what time is it", "how are you"]:
        assert ls.handle_life_note(t) is None
    after = len(ls.load().sayings) + len(ls.load().places) + len(ls.load().loves)
    assert after == before          # nothing captured from questions/chatter


def test_captured_feeds_the_prompt(monkeypatch):
    _fresh(monkeypatch)
    ls.handle_life_note("she always said be kind, always")
    assert "be kind, always" in ls.load().to_prompt()
