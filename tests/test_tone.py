"""
Tests for tone.py + its effect on feel.py — YOUR dial on how Vera delivers.

Proves the dial (a) persists, (b) never moves on its own, and (c) genuinely
changes her stance + voice — each engine works, no hollow shells.
"""

import importlib

import pytest


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", str(tmp_path))
    # reimport so the module picks up the env-based path fresh
    from cognitive_twin import tone
    importlib.reload(tone)
    yield tone
    tone.reset()


def test_default_is_neutral(tmp_store):
    t = tmp_store.get()
    assert t.is_default
    assert t.bluntness == 0.0 and t.warmth == 0.0


def test_set_persists_and_clamps(tmp_store):
    tmp_store.set(bluntness=2.0, warmth=-3.0)   # out of range → clamped
    t = tmp_store.get()
    assert t.bluntness == 1.0 and t.warmth == -1.0
    assert not t.is_default


def test_partial_set_leaves_other_axis(tmp_store):
    tmp_store.set(bluntness=0.5, warmth=0.5)
    tmp_store.set(bluntness=-0.5)               # only bluntness changes
    t = tmp_store.get()
    assert t.bluntness == -0.5 and t.warmth == 0.5


def test_dial_changes_stance(tmp_store):
    from cognitive_twin import feel
    q = "help me figure out the plan"
    base = feel.read(q, apply_tone=False).stance
    tmp_store.set(bluntness=0.9)
    assert feel.read(q).stance.startswith("blunt")
    assert base == feel.read(q, apply_tone=False).stance   # her own read unchanged


def test_dial_changes_voice(tmp_store):
    from cognitive_twin import feel
    q = "let's keep going"
    warm_before = feel.delivery(q)["warmth"]
    tmp_store.set(warmth=-0.8)                  # reserved
    assert feel.delivery(q)["warmth"] < warm_before


def test_dial_reaches_the_directive(tmp_store):
    from cognitive_twin import feel
    tmp_store.set(bluntness=0.9, warmth=-0.7)
    d = feel.directive("what's next")
    assert "blunter" in d.lower()
    assert "reserved" in d.lower()


def test_reset_restores_her_own(tmp_store):
    from cognitive_twin import feel
    q = "help me plan"
    own = feel.read(q, apply_tone=False).stance
    tmp_store.set(bluntness=0.9)
    tmp_store.reset()
    assert feel.read(q).stance == own
    assert tmp_store.get().is_default
