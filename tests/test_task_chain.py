"""
Task chains — Vera turns a goal into an ordered plan and works it step by step.

Start seals a checklist; current is the step she's on; advance/skip move through it;
status reads progress; finishing closes it. Sealed on-device, resumable, and the
STEPS themselves still go through the normal permission gate (this is only the
orchestration). The plan-skills are registered so the agent can call them.
"""
from __future__ import annotations

import tempfile

from cognitive_twin import task_chain as tc


def _fresh(monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())


def test_start_begins_and_seals(monkeypatch, tmp_path):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", str(tmp_path))
    out = tc.start("ship the page", ["draft copy", "build it", "test", "deploy"])
    assert "ship the page" in out and "draft copy" in out
    cur = tc.current()
    assert cur and cur["text"] == "draft copy" and cur["total"] == 4
    f = tmp_path / "task_chain.json"
    if f.exists():
        assert not f.read_bytes().lstrip().startswith(b"{")   # sealed


def test_advance_walks_the_steps(monkeypatch):
    _fresh(monkeypatch)
    tc.start("two step", ["first", "second"])
    assert "first" not in (tc.advance() or "").split("Next")[-1]  # first now done
    cur = tc.current()
    assert cur and cur["text"] == "second"
    done = tc.advance()
    assert "done" in done.lower() or "completes" in done.lower()
    assert tc.current() is None                                  # finished


def test_skip_moves_on(monkeypatch):
    _fresh(monkeypatch)
    tc.start("g", ["a", "b"])
    tc.skip("not needed")
    assert tc.current()["text"] == "b"


def test_status_shows_progress(monkeypatch):
    _fresh(monkeypatch)
    tc.start("g", ["a", "b", "c"])
    tc.advance()
    s = tc.status()
    assert "1/3 done" in s and "✓ a" in s and "▶ b" in s


def test_context_for_prompt_when_active(monkeypatch):
    _fresh(monkeypatch)
    assert tc.context_for_prompt() == ""        # nothing running
    tc.start("goal x", ["step one", "step two"])
    ctx = tc.context_for_prompt()
    assert "PLAN IS IN PROGRESS" in ctx and "step one" in ctx


def test_no_plan_is_graceful(monkeypatch):
    _fresh(monkeypatch)
    assert tc.current() is None
    assert "No active plan" in tc.advance() or "No plan" in tc.status()


def test_skills_registered():
    from cognitive_twin.skills import plan_skill  # noqa: F401 — registers them
    from cognitive_twin.skills.base import default_registry as R
    reg = str(R.__dict__)
    assert "plan_start" in reg and "plan_next" in reg
