"""
Places tests — Vera's location awareness, on-device and gated.

Asserts: (1) intake is refused while disabled/paused (opt-in is real, not
cosmetic), (2) visits are sealed at rest, (3) today/week queries return the right
records in time order, (4) import_visits de-dupes so re-importing an export is
idempotent, (5) the summary reads sensibly. Runs in a temp CTWIN dir.

Run: python -m pytest tests/ -q   (or: python tests/test_places.py)
"""

from __future__ import annotations

import datetime as dt
import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fresh(tmp: Path):
    os.environ["CTWIN_MEMORY_DIR"] = str(tmp)
    from cognitive_twin import vault, security, places
    importlib.reload(vault)
    importlib.reload(security)
    importlib.reload(places)
    vault._key_cache = None
    return places


def _v(place, when, **kw):
    from cognitive_twin.places import Visit
    return Visit(place=place, start=when.isoformat(), **kw)


def test_intake_refused_while_disabled(tmp_path):
    P = _fresh(tmp_path)
    P.disable()
    assert P.record(_v("Secret", dt.datetime.now())) is False
    assert P.read_all() == []


def test_intake_refused_while_paused(tmp_path):
    P = _fresh(tmp_path)
    P.enable()
    P.pause()
    assert P.record(_v("Secret", dt.datetime.now())) is False
    P.resume()
    assert P.record(_v("Home", dt.datetime.now())) is True


def test_visits_sealed_at_rest(tmp_path):
    P = _fresh(tmp_path)
    P.enable()
    P.record(_v("Equinox Bay St", dt.datetime.now(), category="gym"))
    raw = P._log_path().read_bytes()
    assert b"Equinox" not in raw  # sealed


def test_today_and_week_queries(tmp_path):
    P = _fresh(tmp_path)
    P.enable()
    now = dt.datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    P.record(_v("Home", now))
    P.record(_v("Office", now + dt.timedelta(hours=2)))
    P.record(_v("LastWeek", now - dt.timedelta(days=10)))
    today = P.today(now)
    assert [v.place for v in today] == ["Home", "Office"]  # time-ordered, same day
    wk = P.week(now)
    all_week = [v.place for day in wk.values() for v in day]
    assert "Home" in all_week and "LastWeek" not in all_week


def test_import_dedupes(tmp_path):
    P = _fresh(tmp_path)
    P.enable()
    now = dt.datetime.now()
    batch = [_v("Home", now), _v("Gym", now + dt.timedelta(hours=1))]
    assert P.import_visits(batch) == 2
    assert P.import_visits(batch) == 0  # same records → idempotent
    assert len(P.read_all()) == 2


def test_summary_mentions_places(tmp_path):
    P = _fresh(tmp_path)
    P.enable()
    now = dt.datetime.now().replace(hour=8)
    P.record(_v("Home", now, lat=43.65, lon=-79.38))
    P.record(_v("Gym", now + dt.timedelta(hours=2), lat=43.647, lon=-79.381, category="gym"))
    out = P.summarize_day(P.today(now), label="today")
    assert "Home" in out and "Gym" in out and "km" in out


if __name__ == "__main__":
    import tempfile

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            with tempfile.TemporaryDirectory() as d:
                try:
                    fn(Path(d))
                    print(f"  ✓ {name}")
                except AssertionError as e:
                    failures += 1
                    print(f"  ✗ {name}: {e}")
    print("OK" if not failures else f"{failures} FAILED")
    sys.exit(1 if failures else 0)
