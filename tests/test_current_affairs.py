"""
Current-affairs tests — real news, kept relevant to the person, never invented.

She surfaces genuine headlines (BBC RSS through the fenced net doorway), ranks them
to what touches you (your places first, then war/climate/science), keeps partisan
politics down, and returns None when nothing real/relevant is reachable — she never
fabricates news. No network needed here: we patch the fetch.
"""
from __future__ import annotations

import tempfile

from cognitive_twin import proactive


def _fresh(monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())
    proactive.enable_companion(True)


SAMPLE = [
    "Cyclone strengthens as it heads toward the coast of India",
    "New AI chip breaks a performance record",
    "Senator launches re-election campaign with new ad",   # partisan → dropped
    "Musical theatre revival opens in the West End",         # irrelevant → not news
    "Wildfire spreads near Toronto suburbs",
]


def test_politics_is_filtered_out(monkeypatch):
    _fresh(monkeypatch)
    places = proactive._my_places()
    # the campaign item scores -1 (dropped)
    assert proactive._ca_relevant_rank(SAMPLE[2], places) < 0


def test_your_places_rank_highest(monkeypatch):
    _fresh(monkeypatch)
    places = proactive._my_places()
    india = proactive._ca_relevant_rank(SAMPLE[0], places)      # India + cyclone
    toronto = proactive._ca_relevant_rank(SAMPLE[4], places)    # Toronto + wildfire
    chip = proactive._ca_relevant_rank(SAMPLE[1], places)       # relevant, not near you
    assert india > chip and toronto > chip


def test_home_anchors_present(monkeypatch):
    _fresh(monkeypatch)
    places = proactive._my_places()
    for anchor in ("toronto", "india", "canada"):
        assert anchor in places


def test_line_prefers_relevant_and_flags_near_home(monkeypatch):
    _fresh(monkeypatch)
    monkeypatch.setattr(proactive, "_fetch_headlines", lambda: list(SAMPLE))
    line = proactive._current_affairs_line()
    assert line is not None
    # it should pick a near-home event and phrase it as close to home
    assert "close to home" in line
    # and never the partisan or the irrelevant one
    assert "campaign" not in line and "Musical theatre" not in line


def test_none_when_no_real_news(monkeypatch):
    _fresh(monkeypatch)
    # only irrelevant/partisan items → nothing qualifies → None (never invents)
    monkeypatch.setattr(proactive, "_fetch_headlines",
                        lambda: ["Senator launches campaign", "Musical theatre opens"])
    assert proactive._current_affairs_line() is None


def test_none_when_unreachable(monkeypatch):
    _fresh(monkeypatch)
    monkeypatch.setattr(proactive, "_fetch_headlines", lambda: [])
    assert proactive._current_affairs_line() is None
