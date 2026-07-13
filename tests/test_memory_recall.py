"""
Memory recall tests — relevance ranking is a pure function of the query + the
local log, so we seed a temp log (via CTWIN_MEMORY_DIR) and assert what surfaces.
No model, no network.

Run: python -m pytest tests/ -q   (or: python tests/test_memory_recall.py)
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fresh_memory(tmp: str):
    import os
    os.environ["CTWIN_MEMORY_DIR"] = tmp
    # import (or reload) after the env var is set so _dir() picks it up
    import importlib
    from cognitive_twin import memory as m
    importlib.reload(m)
    return m


SEED = [
    ("How do I refactor the voice cloning script?", "use refine.py for XTTS refs"),
    ("Remind me what my mother liked to cook on Sundays", "she loved making biryani"),
    ("What's the best way to deploy the Rust core?", "cargo build then xcframework"),
    ("Tell me about my mother's garden", "roses and tulips by the porch"),
    ("Fix the email triage spam rules", "List-Unsubscribe header signal"),
]


def _seeded():
    tmp = tempfile.mkdtemp()
    m = _fresh_memory(tmp)
    for p, g in SEED:
        m.record(p, g, source="test")
    return m


def test_recall_surfaces_topic_matches():
    m = _seeded()
    hits = m.recall("what did my mother grow in her garden", k=3)
    prompts = " ".join(h["prompt"].lower() for h in hits)
    assert "garden" in prompts          # the most on-topic memory is present
    assert all("rust" not in h["prompt"].lower() for h in hits)  # unrelated excluded


def test_recall_ranks_best_match_first():
    m = _seeded()
    hits = m.recall("my mother's garden flowers", k=2)
    assert hits, "expected at least one hit"
    assert "garden" in hits[0]["prompt"].lower()  # garden beats the cooking memory


def test_recall_empty_query_returns_nothing():
    m = _seeded()
    assert m.recall("", k=3) == []
    assert m.recall("the a an of", k=3) == []  # all stopwords → no signal


def test_context_for_falls_back_to_summary_when_offtopic():
    m = _seeded()
    # a query with no content-word overlap should still yield standing context,
    # not an empty string or an error
    out = m.context_for("xylophone zebra quokka")
    assert out  # falls back to summary_for_prompt(), non-empty with a seeded log


def test_context_for_includes_relevant_memory():
    m = _seeded()
    out = m.context_for("remind me about my mother")
    assert "mother" in out.lower()
    assert "remember" in out.lower()  # uses the recall framing, not just stats


def test_date_query_parses_common_forms():
    import datetime as dt
    m = _seeded()
    today = dt.date.today()
    assert m._parse_date_query("what happened on 2026-07-01") == (dt.date(2026, 7, 1),) * 2
    assert m._parse_date_query("what happened on july 1") == (dt.date(2026, 7, 1),) * 2
    assert m._parse_date_query("tell me about the 1st of July") == (dt.date(2026, 7, 1),) * 2
    y = today - dt.timedelta(days=1)
    assert m._parse_date_query("what did we do yesterday") == (y, y)
    assert m._parse_date_query("what did we talk about earlier today") == (today, today)


def test_date_query_does_not_trigger_on_casual_speech():
    m = _seeded()
    # bare "today" is in half of casual speech — never a date query by itself
    assert m._parse_date_query("I have 3 tasks today") is None
    assert m._parse_date_query("how is mom") is None


def test_recall_by_date_returns_that_days_episodes():
    import datetime as dt
    m = _seeded()  # all seeds recorded "now" → they are today's episodes
    today = dt.date.today()
    hits = m.recall(f"what happened on {today.strftime('%B')} {today.day}")
    assert len(hits) == len(SEED)          # a day deserves a fuller answer
    # topic words rank within the day
    hits = m.recall("what did we say about the garden earlier today")
    assert "garden" in hits[0]["prompt"].lower()


def test_reconsolidation_strengthens_used_memories():
    m = _seeded()
    e = m.recall("my mother's garden", k=1)[0]
    assert m.strength_of(e) == 0
    m.context_for("my mother's garden")    # real use → reinforce
    assert m.strength_of(e) >= 1
    m.clear()                              # clear removes the strength sidecar too
    assert not m._strength_file().exists()


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items())
           if n.startswith("test_") and callable(g)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
