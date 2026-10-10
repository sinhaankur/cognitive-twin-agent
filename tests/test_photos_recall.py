"""
Photos recall — she remembers 'that day' from photo metadata and folds it into
warmth. On-this-day nostalgia, a life-lately prompt block, and a warm check-in
line. Metadata only (never pixels), sealed, honest (empty until she's learned
something; never invents a moment).
"""
from __future__ import annotations

import datetime as _dt
import tempfile

from cognitive_twin import photos


def _fresh(monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())


def _seed_on_this_day(place="Munnar", years_ago=1):
    today = _dt.date.today()
    d = today.replace(year=today.year - years_ago).isoformat()
    photos.learn_moments([{"day": d, "weekday": "Saturday", "part": "afternoon",
                           "place": place, "photos": 20, "spanHours": 4}])


def test_empty_until_learned(monkeypatch):
    _fresh(monkeypatch)
    assert photos.on_this_day() == []
    assert photos.context_for_prompt() == ""
    assert photos.checkin_line() is None


def test_on_this_day_recalls_same_date(monkeypatch):
    _fresh(monkeypatch)
    _seed_on_this_day("Munnar", years_ago=1)
    otd = photos.on_this_day()
    assert otd and "Munnar" in otd[0] and "a year ago today" in otd[0]


def test_on_this_day_ignores_other_dates(monkeypatch):
    _fresh(monkeypatch)
    other = (_dt.date.today() - _dt.timedelta(days=100)).replace(
        year=_dt.date.today().year - 1).isoformat()
    photos.learn_moments([{"day": other, "weekday": "Monday", "part": "morning",
                           "place": "Pune", "photos": 5}])
    assert photos.on_this_day() == []           # not today's calendar day


def test_context_block_references_life(monkeypatch):
    _fresh(monkeypatch)
    _seed_on_this_day("Munnar")
    ctx = photos.context_for_prompt()
    assert "THEIR LIFE LATELY" in ctx and "Munnar" in ctx
    assert "metadata only" in ctx               # the honesty/provenance clause


def test_checkin_line_is_warm_and_real(monkeypatch):
    _fresh(monkeypatch)
    _seed_on_this_day("Munnar")
    line = photos.checkin_line()
    assert line and "Munnar" in line


def test_recent_place_checkin_when_no_on_this_day(monkeypatch):
    _fresh(monkeypatch)
    today = _dt.date.today()
    photos.learn_places([{"region": "Banff", "photos": 30,
                          "first": (today - _dt.timedelta(days=3)).isoformat(),
                          "last": (today - _dt.timedelta(days=2)).isoformat()}])
    line = photos.checkin_line()
    assert line and "Banff" in line
