"""
Mind-graph tests — the live node structure the Mind view draws. Honest: nodes
fire only when they really would, notes are real, edges flow along the true path.
Isolated to a temp dir; no model needed.
"""
from __future__ import annotations

import importlib
import json
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
    import cognitive_twin.life_story as life_story
    import cognitive_twin.brain as brain
    for m in (security, wisdom, life_story, brain):
        importlib.reload(m)
    return brain, wisdom, life_story


def test_resting_graph_has_all_faculties_none_firing():
    brain, _, _ = _fresh()
    g = brain.mind_graph("")
    assert g["nodes"] and g["edges"]
    assert all(n["fires"] is False for n in g["nodes"])   # nothing lit at rest
    assert g["path"] == []
    assert json.dumps(g)                                   # serializable for the API
    print("✓ resting graph: all faculties present, none firing")


def test_emotional_prompt_lights_feel_and_wisdom_in_order():
    brain, wisdom, _ = _fresh()
    wisdom.seed_if_empty()
    g = brain.mind_graph("I feel lost and keep second-guessing everything")
    firing = {n["id"] for n in g["nodes"] if n["fires"]}
    assert "feel" in firing and "wisdom" in firing
    # order is real: memory → feel → … → router → voice
    order = {n["id"]: n["order"] for n in g["nodes"] if n["fires"]}
    assert order["feel"] < order["router"] < order["voice"]
    # the wisdom node carries a TRUE note (it actually retrieved)
    wnote = next(n["note"] for n in g["nodes"] if n["id"] == "wisdom")
    assert "conviction" in wnote
    # at least one edge is flowing along the path
    assert any(e["flowing"] for e in g["edges"])
    print("✓ emotional prompt lights feel + wisdom, in true flow order, with real notes")


def test_neutral_prompt_does_not_light_wisdom_or_life():
    brain, wisdom, life = _fresh()
    wisdom.seed_if_empty()
    life.add_person("Ankur", "son", "")
    g = brain.mind_graph("what is 2 + 2")
    firing = {n["id"] for n in g["nodes"] if n["fires"]}
    assert "wisdom" not in firing      # no conviction performed on a trivial ask
    assert "life" not in firing        # her past isn't dragged into arithmetic
    print("✓ neutral prompt stays lean — no wisdom/life performed on a trivial ask")


def test_memory_prompt_lights_life():
    brain, _, life = _fresh()
    life.add_person("Ankur", "son", "built this")
    g = brain.mind_graph("do you remember when I was small")
    firing = {n["id"] for n in g["nodes"] if n["fires"]}
    assert "life" in firing
    assert next(n["note"] for n in g["nodes"] if n["id"] == "life")
    print("✓ a memory prompt lights the life-story node")


if __name__ == "__main__":
    test_resting_graph_has_all_faculties_none_firing()
    test_emotional_prompt_lights_feel_and_wisdom_in_order()
    test_neutral_prompt_does_not_light_wisdom_or_life()
    test_memory_prompt_lights_life()
    print("\nall mind-graph tests passed")
