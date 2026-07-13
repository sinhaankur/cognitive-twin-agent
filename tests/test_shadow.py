"""
Day-shadow tests. The rule layer and the ledger are pure functions of the text
/ the local event log, so we seed a temp memory dir and assert. No model, no
network, no screen.

Run: python -m pytest tests/ -q   (or: python tests/test_shadow.py)
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fresh():
    """Point the shadow (and memory) at an empty temp dir."""
    os.environ["CTWIN_MEMORY_DIR"] = tempfile.mkdtemp()
    from cognitive_twin import shadow
    return shadow


# ---- the rule layer -------------------------------------------------------------
def test_extracts_commitments_not_questions():
    sh = _fresh()
    assert sh.extract_task("remind me to send the tax form") == "send the tax form"
    assert sh.extract_task("I need to water the plants and then sleep") == "water the plants"
    assert sh.extract_task("todo: refactor the router") == "refactor the router"
    # questions and requests to the agent aren't the user's tasks
    assert sh.extract_task("do I need to buy milk?") == ""
    assert sh.extract_task("can you build the landscape view") == ""
    # "I need to know…" is a question in commitment clothing
    assert sh.extract_task("I need to know how tsne works") == ""


def test_extracts_done_statements():
    sh = _fresh()
    assert sh.extract_done("I finished the tax form") == "the tax form"
    assert sh.extract_done("done with the voice sample") == "the voice sample"
    assert sh.extract_done("how is it done?") == ""


# ---- the ledger -----------------------------------------------------------------
def test_add_dedups_open_tasks():
    sh = _fresh()
    t1, created1 = sh.add("send the tax form")
    t2, created2 = sh.add("Send the tax form.")
    assert created1 and not created2
    assert t2.id == t1.id
    assert len(sh.open_tasks()) == 1


def test_observe_notes_then_crosses_off():
    sh = _fresh()
    note = sh.observe("remind me to send the tax form")
    assert note == "noted: send the tax form"
    # observing the same commitment again is a no-op (dedup)
    assert sh.observe("remind me to send the tax form") == ""
    note = sh.observe("I finished the tax form")
    assert note == "crossed off: send the tax form"
    assert sh.open_tasks() == []
    assert len(sh.done_today()) == 1


def test_complete_matching_picks_best_overlap():
    sh = _fresh()
    sh.add("water the garden plants")
    sh.add("deploy the rust core")
    hit = sh.complete_matching("the rust deploy")
    assert hit is not None and hit.text == "deploy the rust core"
    assert [t.text for t in sh.open_tasks()] == ["water the garden plants"]
    # nothing plausible → nothing crossed off
    assert sh.complete_matching("bake a soufflé") is None


def test_carried_days_show_in_the_view():
    sh = _fresh()
    old = (dt.datetime.now() - dt.timedelta(days=3)).isoformat(timespec="seconds")
    ev = {"ts": old, "ev": "add", "id": "abc12345",
          "text": "water the plants", "source": "heard"}
    with sh._file().open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev) + "\n")
    view = sh.day_view()
    assert "water the plants" in view
    assert "carried 3 days" in view


def test_context_for_prompt_carries_the_day():
    sh = _fresh()
    assert sh.context_for_prompt() == ""
    sh.add("send the tax form")
    ctx = sh.context_for_prompt()
    assert "send the tax form" in ctx
    assert "private" in ctx


def test_memory_record_feeds_the_shadow():
    sh = _fresh()
    import importlib
    from cognitive_twin import memory as m
    importlib.reload(m)
    m.record("remind me to water the plants", "of course — noted.")
    assert [t.text for t in sh.open_tasks()] == ["water the plants"]
    assert sh.open_tasks()[0].source == "heard"


def test_drop_and_clear():
    sh = _fresh()
    sh.add("a task to let go of")
    sh.drop(sh.open_tasks()[0])
    assert sh.open_tasks() == []
    assert sh.clear() is True       # add+drop events were on disk
    assert sh.clear() is False      # nothing left to clear
    assert sh.open_tasks() == []


def test_empty_view_is_safe():
    sh = _fresh()
    view = sh.day_view()
    assert "Nothing on your plate" in view


# ---- seen on screen (the watch → shadow link) -------------------------------------
def test_extract_seen_is_narrow():
    sh = _fresh()
    text = ("some code here\n"
            "# TODO: fix the parser */\n"
            "- [ ] send the deck to sam\n"
            "- [x] already done thing\n"
            "we have a todo list for later\n")   # lowercase prose — not a marker
    assert sh.extract_seen(text) == ["fix the parser", "send the deck to sam"]


def test_propose_keep_ignore_flow():
    sh = _fresh()
    found = sh.propose_from_screen("Code", "// TODO: fix the parser\n")
    assert [p.text for p in found] == ["fix the parser"]
    # same screen again → no re-proposal
    assert sh.propose_from_screen("Code", "// TODO: fix the parser\n") == []
    # a proposal is not a task
    assert sh.open_tasks() == []
    assert "Noticed on your screen" in sh.day_view()
    # keep → becomes a real open task, sourced 'seen'
    sh.keep(sh.proposals()[0])
    assert [t.text for t in sh.open_tasks()] == ["fix the parser"]
    assert sh.open_tasks()[0].source == "seen"
    assert sh.proposals() == []


def test_ignored_sighting_never_returns():
    sh = _fresh()
    sh.propose_from_screen("Notes", "- [ ] water the plants")
    sh.ignore(sh.proposals()[0])
    assert sh.proposals() == []
    # an ignore is an answer — the same sighting stays gone
    assert sh.propose_from_screen("Notes", "- [ ] water the plants") == []
    assert sh.open_tasks() == []


def test_saying_a_proposed_task_resolves_the_sighting():
    sh = _fresh()
    sh.propose_from_screen("Code", "TODO: fix the parser")
    # the user commits to it in conversation — the sighting is answered
    sh.observe("remind me to fix the parser")
    assert [t.text for t in sh.open_tasks()] == ["fix the parser"]
    assert sh.proposals() == []


def test_welcome_back_mentions_pending_sightings(tmp_path=None):
    sh = _fresh()
    import tempfile as _tf
    notes = Path(_tf.mkdtemp()) / "watch-notes.md"
    notes.write_text("### 2026-07-13 09:14:02 — Code  _(via ocr)_\nsome text\n",
                     encoding="utf-8")
    os.environ["CTWIN_WATCH_FILE"] = str(notes)
    try:
        sh.propose_from_screen("Code", "TODO: fix the parser")
        from cognitive_twin import watch_review
        out = watch_review.welcome_back(use_llm=False)
        assert "1 possible task(s)" in out
    finally:
        del os.environ["CTWIN_WATCH_FILE"]


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items())
           if n.startswith("test_") and callable(g)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
