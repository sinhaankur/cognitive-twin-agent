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


if __name__ == "__main__":
    test_empty_is_silent()
    test_seed_then_retrieve_relevant()
    test_context_block_has_guardrails()
    test_own_beliefs_add_and_dedupe_and_seal()
    print("\nall wisdom tests passed")
