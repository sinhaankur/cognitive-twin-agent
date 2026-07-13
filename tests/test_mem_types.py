"""
Memory-type + landscape tests. The classifier and layout are pure functions of
the text / the local log, so we seed a temp memory dir and assert. No model, no
network, no screen.

Run: python -m pytest tests/ -q   (or: python tests/test_mem_types.py)
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cognitive_twin import mem_types as mt  # noqa: E402


def test_emotion():
    assert mt.classify("I miss my mother so much") == mt.EMOTION
    assert mt.classify("feeling tired today") == mt.EMOTION


def test_task():
    assert mt.classify("remind me to build the landscape view") == mt.TASK
    assert mt.classify("fix the failing tests") == mt.TASK


def test_opinion():
    assert mt.classify("I think Rust is better than Go") == mt.OPINION
    assert mt.classify("I love how this app is built") == mt.OPINION


def test_knowledge_is_default():
    assert mt.classify("How does t-SNE reduce dimensions?") == mt.KNOWLEDGE
    assert mt.classify("the capital of France") == mt.KNOWLEDGE


def test_every_type_has_color_and_label():
    for t in mt.TYPES:
        assert mt.color(t).startswith("#")
        assert mt.label(t)


def test_landscape_positions_and_types():
    # fresh temp memory dir; reload memory so it picks up the env var
    os.environ["CTWIN_MEMORY_DIR"] = tempfile.mkdtemp()
    import importlib
    from cognitive_twin import memory as m
    importlib.reload(m)
    from cognitive_twin import brain
    for text in ["I miss my mother", "my mother's garden roses",
                 "remind me to deploy rust", "rust cargo build core",
                 "how does tsne work"]:
        m.record(text, "")
    ls = brain.landscape()
    assert ls["count"] == 5
    # every point is normalized into [0,1] and carries a type + colour
    for p in ls["points"]:
        assert 0.0 <= p["x"] <= 1.0 and 0.0 <= p["y"] <= 1.0
        assert p["type"] in mt.TYPES
        assert p["color"].startswith("#")
    # type tallies present for all kinds
    assert set(ls["types"].keys()) == set(mt.TYPES)


def test_landscape_empty_is_safe():
    os.environ["CTWIN_MEMORY_DIR"] = tempfile.mkdtemp()
    import importlib
    from cognitive_twin import memory as m
    importlib.reload(m)
    from cognitive_twin import brain
    ls = brain.landscape()
    assert ls["points"] == []


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items())
           if n.startswith("test_") and callable(g)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
