"""
Companion check-in tests — Vera reaching out on her own (the 'yapper' layer).

She should: be OFF by default; when on, vary her lines across flavours (warmth,
emotion, care, jokes, ideas, everyday); NEVER joke in a heavy moment; respect the
cadence + quiet hours; and store nothing but a last-spoken timestamp + a short
recent-line memory so she rotates. Speaking is best-effort and never required here.
"""
from __future__ import annotations

import os
import tempfile

from cognitive_twin import proactive


def _fresh(monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())


def test_companion_off_by_default(monkeypatch):
    _fresh(monkeypatch)
    assert proactive.companion_enabled() is False
    # not enabled → never due, never a line
    assert proactive.companion_checkin(speak=False) is None


def _awake(monkeypatch):
    """Force not-quiet-hours + no device hold-back, so the test exercises the
    check-in LOGIC rather than the wall-clock (she's silent at night by design)."""
    monkeypatch.setattr(proactive, "_in_quiet_hours", lambda h: False)
    import cognitive_twin.presence as _p
    monkeypatch.setattr(_p, "device_now",
                        lambda: {"activity": "unknown", "should_interject": True, "confidence": 0.0})


def test_enable_then_due_and_speaks_a_line(monkeypatch):
    _fresh(monkeypatch)
    _awake(monkeypatch)
    proactive.enable_companion(True)
    assert proactive.companion_enabled() is True
    line = proactive.companion_checkin(speak=False)   # due on a fresh store
    assert isinstance(line, str) and len(line) > 0


def test_cadence_blocks_a_second_line_right_away(monkeypatch):
    _fresh(monkeypatch)
    _awake(monkeypatch)
    proactive.enable_companion(True)
    first = proactive.companion_checkin(speak=False)
    assert first
    # immediately after, it's not due again (the cadence gate)
    assert proactive.companion_checkin(speak=False) is None


def test_no_jokes_when_heavy(monkeypatch):
    _fresh(monkeypatch)
    proactive.enable_companion(True)
    monkeypatch.setattr(proactive, "_current_mood", lambda: "heavy")
    jokes = set(proactive._COMPANION_BANK["joke"])
    everyday = set(proactive._COMPANION_BANK["everyday"])
    # sample many picks; a heavy mood must never surface a joke or chit-chat
    for _ in range(40):
        line = proactive._pick_companion_line()
        assert line not in jokes
        assert line not in everyday


def test_story_flavours_only_when_light(monkeypatch):
    """The lean-in story/dilemma/curio lines are engaging, but would feel flippant
    in a hard moment — so they're light-mood only."""
    _fresh(monkeypatch)
    proactive.enable_companion(True)
    story = (set(proactive._COMPANION_BANK["story"])
             | set(proactive._COMPANION_BANK["dilemma"])
             | set(proactive._COMPANION_BANK["curio"]))
    # heavy: never a story
    monkeypatch.setattr(proactive, "_current_mood", lambda: "heavy")
    for _ in range(50):
        assert proactive._pick_companion_line() not in story
    # light: they DO show up across many picks
    monkeypatch.setattr(proactive, "_current_mood", lambda: "light")
    seen_story = any(proactive._pick_companion_line() in story for _ in range(80))
    assert seen_story


def test_light_mood_has_range(monkeypatch):
    _fresh(monkeypatch)
    proactive.enable_companion(True)
    monkeypatch.setattr(proactive, "_current_mood", lambda: "light")
    seen = {proactive._pick_companion_line() for _ in range(60)}
    # across many picks she should draw from more than one flavour
    flavours_hit = sum(
        1 for fl, lines in proactive._COMPANION_BANK.items()
        if seen & set(lines)
    )
    assert flavours_hit >= 3


def test_quiet_hours_suppress(monkeypatch):
    _fresh(monkeypatch)
    proactive.enable_companion(True)
    monkeypatch.setattr(proactive, "_in_quiet_hours", lambda h: True)
    assert proactive.companion_checkin(speak=False) is None


def test_current_affairs_is_none_without_research(monkeypatch):
    _fresh(monkeypatch)
    # no research module / not enabled → she never invents news, returns None
    assert proactive._current_affairs_line() is None
