"""
Health care — Vera's care, grounded in a real Apple Health summary (opt-in).

She praises consistency, gently nudges a long gap (never scolds), honours rest,
and feeds a 'how their body's been' block to the prompt. Off by default; summary
metadata only; empty/None until given an export; never invents.
"""
from __future__ import annotations

import datetime as _dt
import tempfile

from cognitive_twin import health


def _fresh(monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())


def _seed(monkeypatch, summary):
    _fresh(monkeypatch)
    health.enable(True)
    health._save(summary)


def test_off_by_default(monkeypatch):
    _fresh(monkeypatch)
    assert health.is_enabled() is False
    assert health.checkin_line() is None
    assert health.context_for_prompt() == ""


def test_consistency_is_praised(monkeypatch):
    _seed(monkeypatch, {"total_workouts": 40, "active_days_30d": 20,
                        "avg_steps_30d": 9000,
                        "last_workout": _dt.date.today().isoformat()})
    line = health.checkin_line()
    assert line and ("take" in line.lower() or "glad" in line.lower())


def test_long_gap_is_a_gentle_nudge(monkeypatch):
    old = (_dt.date.today() - _dt.timedelta(days=8)).isoformat()
    _seed(monkeypatch, {"total_workouts": 10, "active_days_30d": 8,
                        "avg_steps_30d": 4000, "last_workout": old})
    line = health.checkin_line()
    assert line and "no pressure" in line.lower()


def test_light_activity_is_a_soft_invitation(monkeypatch):
    _seed(monkeypatch, {"total_workouts": 5, "active_days_30d": 4,
                        "avg_steps_30d": 3000,
                        "last_workout": _dt.date.today().isoformat()})
    line = health.checkin_line()
    assert line and "?" in line                 # an invitation, not a command


def test_context_block_grounds_care(monkeypatch):
    _seed(monkeypatch, {"total_workouts": 40, "active_days_30d": 20,
                        "avg_steps_30d": 9000,
                        "last_workout": _dt.date.today().isoformat(),
                        "top_workouts": [{"type": "Running", "count": 15}]})
    ctx = health.context_for_prompt()
    assert "HOW THEY'VE BEEN PHYSICALLY" in ctx and "summary only" in ctx


def test_summary_is_sealed(monkeypatch, tmp_path):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", str(tmp_path))
    health.enable(True)
    health._save({"total_workouts": 3, "active_days_30d": 2})
    f = tmp_path / "health.json"
    if f.exists():
        raw = f.read_bytes()
        assert not raw.lstrip().startswith(b"{")
