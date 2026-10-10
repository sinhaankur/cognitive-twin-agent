"""
Learned proactivity timing — Vera learns WHEN her reaching out is welcome.

A warm reply to a check-in makes her reach out more in that context; a dismissal
or being ignored makes her ease off. Gentle (one turn never swings it), bounded
(never naggy, never silent), on-device + sealed, and a no-op unless she actually
made a check-in that's awaiting a response.
"""
from __future__ import annotations

import tempfile
import time

from cognitive_twin import proactive, security


def _fresh(monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())
    proactive.enable_companion(True)


def _pending(ctx, at=None):
    st = proactive._companion_state()
    st["pending"] = {"ctx": ctx, "at": at if at is not None else time.time()}
    security.write_state(security.path(proactive._COMPANION_FILE), st)


def test_unknown_context_is_neutral(monkeypatch):
    _fresh(monkeypatch)
    assert proactive._welcome("afternoon") == 0.5
    # neutral cadence sits inside the bounds
    c = proactive._cadence_min("afternoon")
    assert proactive._CADENCE_MIN_MIN <= c <= proactive._CADENCE_MAX_MIN


def test_warm_reply_shortens_cadence(monkeypatch):
    _fresh(monkeypatch)
    before = proactive._cadence_min("afternoon")
    for _ in range(3):
        _pending("afternoon")
        proactive.note_response("thank you, I love hearing from you")
    after = proactive._cadence_min("afternoon")
    assert proactive._welcome("afternoon") > 0.6
    assert after < before                      # she reaches out MORE when welcome


def test_dismissal_lengthens_cadence(monkeypatch):
    _fresh(monkeypatch)
    before = proactive._cadence_min("evening")
    for _ in range(3):
        _pending("evening")
        proactive.note_response("not now, leave me alone")
    after = proactive._cadence_min("evening")
    assert proactive._welcome("evening") < 0.45
    assert after > before                      # she backs off when brushed off


def test_ignored_eases_off(monkeypatch):
    _fresh(monkeypatch)
    _pending("morning", at=time.time() - 300)  # past the response window
    proactive.note_ignored()
    assert proactive._welcome("morning") < 0.5


def test_gentle_one_turn_does_not_swing(monkeypatch):
    _fresh(monkeypatch)
    _pending("afternoon")
    proactive.note_response("thanks")
    # one warm turn nudges, doesn't jump to the ceiling
    assert 0.5 < proactive._welcome("afternoon") < 0.75


def test_no_pending_is_noop(monkeypatch):
    _fresh(monkeypatch)
    proactive.note_response("hello there")     # no check-in awaiting a reply
    assert proactive._welcome("afternoon") == 0.5


def test_cadence_stays_within_bounds(monkeypatch):
    _fresh(monkeypatch)
    # hammer warm until saturated
    for _ in range(30):
        _pending("afternoon")
        proactive.note_response("I love this, so sweet, thank you")
    c = proactive._cadence_min("afternoon")
    assert c >= proactive._CADENCE_MIN_MIN     # never naggier than the floor
