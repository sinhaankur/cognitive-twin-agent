"""
Tests for mirror.py — her voice adapts to how you speak, but stays her.

Proves the accommodation engine works: it measures your style, learns it slowly,
leans her delivery + wording toward you, and — critically — the identity FLOOR
holds so she never copies you outright.
"""

import importlib

import pytest


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", str(tmp_path))
    from cognitive_twin import mirror
    importlib.reload(mirror)
    return mirror


def test_measure_terse_vs_verbose(store):
    terse = store.measure("do it")
    verbose = store.measure("could you please walk me through the entire plan step "
                            "by step so I understand exactly what happens and why")
    assert terse.brevity > verbose.brevity


def test_measure_energy_and_register(store):
    assert store.measure("YES let's GO!!").energy > store.measure("okay. fine.").energy
    casual = store.measure("yeah nah lol dude kinda cool")
    formal = store.measure("therefore the implementation shall proceed accordingly")
    assert casual.formality < formal.formality


def test_profile_learns_slowly_and_persists(store):
    for _ in range(8):
        store.observe("YES!! let's GO, so excited!!")
    p = store.profile()
    assert p.energy > 0.7                       # learned a lively style
    # persisted: a fresh read returns the same profile
    assert store.profile().energy == p.energy


def test_lean_is_bounded_by_the_floor(store):
    for _ in range(10):
        store.observe("YES!! GO GO GO, amazing!!")
    lean = store.lean()
    assert lean["amount"] == 0.30
    # 30% × (energy delta ≤ 0.5) → the lean stays a tint, not a takeover
    assert abs(lean["energy"]) <= 0.35


def test_lean_amount_cannot_exceed_halfway(store, monkeypatch):
    monkeypatch.setenv("CTWIN_MIRROR_LEAN", "0.99")
    assert store.lean()["amount"] == 0.5        # hard floor


def test_delivery_leans_toward_a_lively_user(store):
    from cognitive_twin import feel
    calm = feel.delivery("okay, sounds fine")   # neutral baseline (empty profile)
    for _ in range(10):
        store.observe("YES!! let's GO!!")
    lively = feel.delivery("okay, sounds fine")
    assert lively["speed"] >= calm["speed"]


def test_directive_carries_register_nudge(store):
    from cognitive_twin import feel
    for _ in range(10):
        store.observe("Therefore the implementation shall proceed accordingly.")
    d = feel.directive("what is next")
    assert "register is formal" in d.lower()


def test_default_profile_is_neutral_noop(store):
    # never observed → lean is ~0 on every axis (she's fully herself)
    lean = store.lean()
    assert all(abs(lean[k]) < 1e-6 for k in ("energy", "brevity", "formality", "warmth"))
