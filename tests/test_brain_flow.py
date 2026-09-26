"""
Brain-flow tests (Companion Charter §6) — behaviour is produced by the organs in
order (limbic → hippocampus → frontal → cortex), with the LLM as the last step.
Isolated to a temp memory dir.
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
    from cognitive_twin import security, mental_model, brain_flow
    importlib.reload(security)
    importlib.reload(mental_model)
    importlib.reload(brain_flow)
    return brain_flow, mental_model


def test_cortex_is_always_last():
    brain_flow, _ = _fresh()
    flow = brain_flow.compose("I feel lonely and sad today.")
    assert flow.steps[-1] == "cortex(LLM)", flow.steps
    print("✓ cortex (the LLM) is always the last organ")


def test_limbic_fires_on_a_feeling_turn():
    brain_flow, _ = _fresh()
    flow = brain_flow.compose("I feel so lonely and overwhelmed.")
    assert "limbic+frontal" in flow.steps
    # the felt state must be handed to the model, decided by her own logic
    assert "HOW YOU FEEL RIGHT NOW" in flow.as_prompt()
    print("✓ limbic+frontal fire on a feeling turn (felt state handed to the model)")


def test_hippocampus_recalls_the_person():
    brain_flow, mm = _fresh()
    # teach the model something, then a later turn should recall it
    mm.observe("I miss my mother so much.")
    mm.observe("I've been really lonely lately.")
    flow = brain_flow.compose("How are you?")
    assert "hippocampus" in flow.steps
    p = flow.as_prompt()
    assert "mother" in p or "lonely" in p or "grief" in p
    print("✓ hippocampus recalls what she knows about the person")


def test_order_is_limbic_then_hippocampus():
    brain_flow, mm = _fresh()
    mm.observe("I miss my dad.")
    flow = brain_flow.compose("I feel sad and I miss him.")
    # limbic must come before hippocampus before cortex
    li = flow.steps.index("limbic+frontal")
    hi = flow.steps.index("hippocampus")
    co = flow.steps.index("cortex(LLM)")
    assert li < hi < co, flow.steps
    print("✓ charter order: limbic → hippocampus → cortex")


def test_blank_turn_still_ends_at_cortex():
    brain_flow, _ = _fresh()
    # a flat, unknown turn: organs may stay quiet, but cortex handoff is always noted
    flow = brain_flow.compose("ok")
    assert flow.steps[-1] == "cortex(LLM)"
    print("✓ even a flat turn ends at the cortex handoff (fail-soft)")


def test_explain_is_honest():
    brain_flow, mm = _fresh()
    mm.observe("I feel lonely.")
    line = brain_flow.explain("I feel lonely and miss my mom.")
    assert line.startswith("brain-flow ·")
    assert "cortex(LLM)" in line
    print("✓ explain() traces the organs that actually fired")


if __name__ == "__main__":
    test_cortex_is_always_last()
    test_limbic_fires_on_a_feeling_turn()
    test_hippocampus_recalls_the_person()
    test_order_is_limbic_then_hippocampus()
    test_blank_turn_still_ends_at_cortex()
    test_explain_is_honest()
    print("\nALL BRAIN-FLOW TESTS PASSED")
