"""
Wisdom tests — her mind: convictions, RETRIEVED to fit the moment. Honest when
empty (never performs wisdom she doesn't hold), relevant when it fits, sealed at
rest. Keyword path exercised (no embed model needed); CTWIN_NO_UNHOSTED offline.
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fresh():
    d = tempfile.mkdtemp()
    os.environ["CTWIN_MEMORY_DIR"] = d
    os.environ["CTWIN_PERSONA_DIR"] = d
    os.environ["CTWIN_NO_UNHOSTED"] = "1"
    import cognitive_twin.security as security
    import cognitive_twin.wisdom as wisdom
    for m in (security, wisdom):
        importlib.reload(m)
    return wisdom, Path(d)


def test_empty_is_silent():
    w, _ = _fresh()
    assert w.load().is_empty() is True
    assert w.retrieve("I'm so anxious about everything") == []
    assert w.context_for_prompt("anything") == ""   # never invents a belief
    assert "none yet" in w.status()
    print("✓ empty wisdom → silent (never performs wisdom she doesn't hold)")


def test_seed_then_retrieve_relevant():
    w, _ = _fresh()
    n = w.seed_if_empty()
    assert n > 0
    assert w.seed_if_empty() == 0          # idempotent — won't double-seed

    # an anxious/worry moment should surface the worry conviction, not the rest
    hits = w.retrieve("I can't stop worrying about the future", k=2)
    assert hits, "expected a relevant conviction for a worry moment"
    assert any("worry" in h.text.lower() or "worry" in h.about.lower() for h in hits)

    # a rest/burnout moment should surface the rest conviction
    hits2 = w.retrieve("I'm completely burnt out and exhausted", k=2)
    assert any("rest" in h.text.lower() or "empty" in h.text.lower() for h in hits2)
    print("✓ seeds a starter mind + retrieves the conviction that fits the moment")


def test_context_block_has_guardrails():
    w, _ = _fresh()
    w.seed_if_empty()
    block = w.context_for_prompt("I keep second-guessing every decision", k=2)
    assert block
    assert "HER MIND" in block
    # must tell the model not to preach / recite / invent
    assert "never" in block.lower()
    assert "invent" in block.lower() or "force" in block.lower()
    print("✓ retrieved-wisdom prompt block carries the don't-preach/don't-invent guardrails")


def test_own_beliefs_add_and_dedupe_and_seal():
    w, d = _fresh()
    w.add("Money is a tool for taking care of people, never a scoreboard.", about="money wealth greed")
    w.add("Money is a tool for taking care of people, never a scoreboard.")  # dup
    assert len(w.load().beliefs) == 1
    # sealed at rest — the plaintext belief must not sit on disk
    raw = (d / "wisdom.json").read_bytes()
    assert b"scoreboard" not in raw
    # reads back through the kernel
    assert any("scoreboard" in b.text for b in w.load().beliefs)
    # and it retrieves for a money moment
    hits = w.retrieve("should I take the higher-paying job I'll hate", k=2)
    assert any("money" in h.about.lower() or "tool" in h.text.lower() for h in hits)
    print("✓ her own convictions add, dedupe, seal at rest, and retrieve")


def _fresh_with_memory():
    """Fresh dirs + a memory log carrying a couple of belief statements."""
    w, d = _fresh()
    import cognitive_twin.memory as memory
    importlib.reload(memory)
    memory.record("I truly believe family comes before everything else", "noted")
    memory.record("what matters most to me is being honest even when it costs", "noted")
    memory.record("what's the weather like", "it's clear")   # NOT a conviction
    return w, memory, d


def test_learns_proposals_but_never_auto_adds():
    w, _, _ = _fresh_with_memory()
    n = w.scan_for_convictions()
    assert n >= 2, "should propose the two belief statements"
    # crucially: proposing does NOT change her actual convictions
    assert w.load().is_empty() is True
    props = w.proposals()
    texts = " ".join(p["text"].lower() for p in props)
    assert "family" in texts
    assert "honest" in texts
    assert "weather" not in texts            # a plain question is not a conviction
    print("✓ learns proposals from real talk, never auto-adds (human-in-the-loop)")


def test_approve_promotes_one_proposal():
    w, _, _ = _fresh_with_memory()
    w.scan_for_convictions()
    before = len(w.load().beliefs)
    kept = w.approve_proposal(0, about="family values")
    assert kept
    assert len(w.load().beliefs) == before + 1
    # approved one leaves the queue
    assert all(p["text"] != kept for p in w.proposals())
    # and it's now retrievable like any conviction
    assert w.retrieve(kept, k=1)
    print("✓ approving a proposal promotes it into her real, retrievable convictions")


def test_scan_is_idempotent():
    w, _, _ = _fresh_with_memory()
    first = w.scan_for_convictions()
    again = w.scan_for_convictions()
    assert again == 0, "re-scanning the same memory shouldn't duplicate proposals"
    assert len(w.proposals()) == first
    print("✓ re-scanning doesn't duplicate proposals")


if __name__ == "__main__":
    test_empty_is_silent()
    test_seed_then_retrieve_relevant()
    test_context_block_has_guardrails()
    test_own_beliefs_add_and_dedupe_and_seal()
    test_learns_proposals_but_never_auto_adds()
    test_approve_promotes_one_proposal()
    test_scan_is_idempotent()
    print("\nall wisdom tests passed")
