"""
Tests for feel.py — Vera's felt-state layer (limbic + frontal), no LLM.

Proves the feeling and the stance are decided by Vera's own deterministic logic,
so she works with or without a model / the internet.
"""

from cognitive_twin import feel


def test_reads_heavy_and_chooses_gentle():
    f = feel.read("I feel so lonely and exhausted today")
    assert f.is_heavy
    assert f.valence < 0
    assert f.stance.startswith("gentle")
    assert "hold-space" in f.stance          # don't rush to fix a hard moment


def test_reads_light_and_playful():
    f = feel.read("we finally shipped it, so excited!")
    assert f.is_light
    assert f.valence > 0


def test_planning_gets_a_recommendation_stance():
    f = feel.read("what should I focus on next")
    assert "recommend" in f.stance           # frontal lobe leads with a call


def test_neutral_turn_produces_no_directive():
    # don't manufacture emotion on flat, factual turns
    assert feel.directive("what is 2 + 2") == ""
    assert feel.directive("list my projects") == ""


def test_heavy_turn_produces_a_gentle_directive():
    d = feel.directive("I feel worried and stuck")
    assert d                                  # she has a felt state to hand over
    assert "gentle" in d.lower()
    assert "never announce it" in d.lower()   # live the feeling, don't state it


def test_directive_is_deterministic_offline():
    # same input → same felt directive, every time, with no network/model
    a = feel.directive("I'm proud of what we built")
    b = feel.directive("I'm proud of what we built")
    assert a == b
