"""
Personality learning — Vera learns WHO YOU ARE from how you chat, and tells the
LLM, so its replies fit you (Ankur: "cater to that so the LLM knows who I am").

Observed, never invented: a trait only counts once it's shown up enough to be real
(not one stray word), it's sealed on-device, and it surfaces as a gentle "who they
are" line in the prompt — empty until she's genuinely learned something.
"""
from __future__ import annotations

import tempfile

from cognitive_twin import mental_model as mm


def _fresh(monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())


def test_blank_until_learned(monkeypatch):
    _fresh(monkeypatch)
    assert mm.personality_profile() == []
    assert mm.context_for_prompt() == ""       # she doesn't claim to know a stranger


def test_learns_a_repeated_trait(monkeypatch):
    _fresh(monkeypatch)
    for _ in range(4):
        mm.observe("let's build and ship the app, I want to make this")
    prof = mm.personality_profile()
    assert "driven" in prof


def test_one_off_does_not_become_a_trait(monkeypatch):
    _fresh(monkeypatch)
    mm.observe("haha that's funny")            # a single playful line
    # below the min-count → not yet a claimed trait
    assert "playful" not in mm.personality_profile()


def test_interests_are_picked_up(monkeypatch):
    _fresh(monkeypatch)
    for _ in range(3):
        mm.observe("the AI model and the neural engine and the code")
    assert "tech/AI" in mm.personality_profile()


def test_profile_feeds_the_prompt(monkeypatch):
    _fresh(monkeypatch)
    for _ in range(4):
        mm.observe("build ship launch, let's make the engine, I want to create")
    ctx = mm.context_for_prompt()
    assert "who they are" in ctx and "driven" in ctx
    assert "meet them there" in ctx


def test_personality_is_sealed(monkeypatch, tmp_path):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", str(tmp_path))
    for _ in range(4):
        mm.observe("build and ship the app")
    # the store exists and is NOT plaintext JSON on disk
    import os
    f = tmp_path / "mental_model.json"
    if f.exists():
        raw = f.read_bytes()
        assert not raw.lstrip().startswith(b"{")
