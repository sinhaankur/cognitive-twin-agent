"""
Mental-model tests — the living, deterministic model of the person (Charter §3).
Isolated to a temp memory dir so it never touches the real one.
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fresh():
    os.environ["CTWIN_MEMORY_DIR"] = tempfile.mkdtemp()
    from cognitive_twin import security, mental_model
    importlib.reload(security)
    importlib.reload(mental_model)
    return mental_model


def test_blank_model_is_silent():
    mm = _fresh()
    assert mm.context_for_prompt() == ""   # she doesn't pretend to know a stranger
    print("✓ blank model stays silent (no invented backstory)")


def test_observes_feelings_people_threads():
    mm = _fresh()
    mm.observe("I feel so lonely lately, and I really miss my mother.")
    mm.observe("Work is overwhelming, the deadline for my project is crushing me.")
    mm.observe("Still overwhelmed by that project deadline honestly.")
    ctx = mm.context_for_prompt()
    assert "lonely" in ctx or "grief" in ctx
    assert "overwhelmed" in ctx
    assert "mother" in ctx
    # the repeated project/deadline turns should merge into one live thread
    data = mm.load()
    assert data["turns"] == 3
    assert any(t.get("hits", 0) >= 2 for t in data["threads"]), "recurring thread not merged"
    print("✓ observes feelings, people, and merges recurring threads")


def test_is_deterministic():
    mm = _fresh()
    mm.observe("I'm anxious about tomorrow.")
    a = mm.context_for_prompt()
    b = mm.context_for_prompt()
    assert a == b   # no randomness — her memory is stable + auditable
    print("✓ deterministic recall")


def test_is_sealed_on_disk():
    mm = _fresh()
    mm.observe("I miss my dad.")
    from cognitive_twin import security
    p = security.path("mental_model.json")
    raw = p.read_bytes()
    # the raw file must NOT contain the plaintext — it's sealed by the kernel
    assert b"miss my dad" not in raw and b"dad" not in raw, "personal state left unsealed!"
    # but reading through the kernel returns it
    assert "dad" in mm.context_for_prompt()
    print("✓ state is sealed at rest, readable through the kernel")


def test_clear_forgets():
    mm = _fresh()
    mm.observe("I feel proud of finishing.")
    assert mm.context_for_prompt() != ""
    assert mm.clear() is True
    assert mm.context_for_prompt() == ""
    print("✓ clear() forgets the person")


if __name__ == "__main__":
    test_blank_model_is_silent()
    test_observes_feelings_people_threads()
    test_is_deterministic()
    test_is_sealed_on_disk()
    test_clear_forgets()
    print("\nALL MENTAL-MODEL TESTS PASSED")
