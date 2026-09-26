"""
Life-memory tests (Companion Charter §7) — RAG grounded in real shared history,
sealed at rest, honest when empty. Isolated to a temp memory dir; no embed model
required (keyword path is exercised; CTWIN_NO_UNHOSTED keeps it offline).
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
    os.environ["CTWIN_NO_UNHOSTED"] = "1"
    # import THEN reload, so this works no matter what earlier tests left in
    # sys.modules (reload() requires the module to already be imported).
    import cognitive_twin.security as security
    import cognitive_twin.memory as memory
    import cognitive_twin.life_memory as life_memory
    import cognitive_twin.brain_flow as brain_flow
    for m in (security, memory, life_memory, brain_flow):
        importlib.reload(m)
    return memory, life_memory, brain_flow


def test_empty_history_is_silent():
    _, lm, _ = _fresh()
    assert lm.available() is False
    assert lm.retrieve("anything") == []
    assert lm.context_for_prompt("anything") == ""   # no invented memory
    print("✓ empty history → silent (no fabricated memory)")


def test_builds_and_recalls_real_moments():
    memory, lm, _ = _fresh()
    memory.record("I'm planning a trip to Kyoto in spring.", "That sounds lovely — the blossoms.")
    memory.record("Work has been stressful this week.", "I hear that. Be gentle with yourself.")
    info = lm.build_index()
    assert info["count"] >= 2
    assert lm.available() is True
    hits = lm.retrieve("tell me about my Kyoto trip")
    assert hits, "should recall the Kyoto moment"
    assert "kyoto" in hits[0].text.lower()
    print("✓ builds from real history and recalls the right moment")


def test_index_is_sealed_on_disk():
    memory, lm, _ = _fresh()
    memory.record("My secret plan is to move to Kyoto.", "Ok.")
    lm.build_index()
    from cognitive_twin import security
    p = security.path("life_memory_index.json")
    raw = p.read_bytes()
    assert b"Kyoto" not in raw and b"secret plan" not in raw, "life-memory left UNSEALED!"
    # but recall through the kernel still works
    assert lm.retrieve("kyoto"), "sealed index should still be readable via the kernel"
    print("✓ life-memory index is sealed at rest, readable only via the kernel")


def test_wired_into_hippocampus():
    memory, lm, brain_flow = _fresh()
    memory.record("I adopted a dog named Biscuit.", "Biscuit! What a good name.")
    lm.build_index()
    flow = brain_flow.compose("what's my dog's name again?")
    p = flow.as_prompt()
    assert "hippocampus" in flow.steps
    assert "biscuit" in p.lower(), "life-memory recall should reach the brain flow"
    print("✓ life-memory flows through the hippocampus step of the brain")


def test_clear_forgets():
    memory, lm, _ = _fresh()
    memory.record("Remember my anniversary is in June.", "I will.")
    lm.build_index()
    assert lm.available()
    assert lm.clear() is True
    assert lm.available() is False
    print("✓ clear() forgets the shared history")


if __name__ == "__main__":
    test_empty_history_is_silent()
    test_builds_and_recalls_real_moments()
    test_index_is_sealed_on_disk()
    test_wired_into_hippocampus()
    test_clear_forgets()
    print("\nALL LIFE-MEMORY TESTS PASSED")
