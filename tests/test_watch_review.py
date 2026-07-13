"""
Watch-review tests — parsing notes and rolling them up are pure functions of the
notes text, so we feed sample notes and assert. No screen, no LLM.

Run: python -m pytest tests/ -q   (or: python tests/test_watch_review.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cognitive_twin import watch_review as wr  # noqa: E402

NOTES = """## Watch session started 2026-07-13 09:00:00 (every 60s, read-only)

### 2026-07-13 09:00:05 — Code  _(via ocr)_

> def main(): ...
> TODO: fix the parser

### 2026-07-13 09:03:05 — Code  _(via ocr)_

> tests failing on line 42

### 2026-07-13 09:05:00 — Terminal  _(via ax)_

> $ pytest -q
> 2 failed

## Watch session ended 2026-07-13 09:06:00 — 3 observation(s)
"""


def test_parse_extracts_observations():
    r = wr.parse(NOTES)
    assert len(r.observations) == 3
    assert r.observations[0].app == "Code"
    assert r.observations[0].strategy == "ocr"
    assert "TODO: fix the parser" in r.observations[0].body
    assert r.observations[2].app == "Terminal"


def test_session_banner_does_not_become_an_observation():
    r = wr.parse(NOTES)
    assert all("Watch session" not in o.app for o in r.observations)


def test_span_and_apps():
    r = wr.parse(NOTES)
    assert "09:00:05" in r.span and "09:05:00" in r.span
    apps = dict(r.apps)
    assert apps["Code"] == 2 and apps["Terminal"] == 1


def test_time_in_app_reflects_gaps_not_counts():
    r = wr.parse(NOTES)
    spent = dict(r.time_in_app)
    # Code spans 09:00→09:05 (~5 min held), Terminal is the trailing obs (~0)
    assert spent["Code"] > spent["Terminal"]
    assert spent["Code"] >= 4.5


def test_rollup_reads_as_time_not_obs_count():
    r = wr.parse(NOTES)
    out = wr.rollup(r)
    assert "Where your time went" in out
    assert "min" in out


def test_empty_notes_message():
    r = wr.Review()
    out = wr.rollup(r)
    assert "No watch notes yet" in out


def test_parse_since_hhmm_and_iso():
    assert wr._parse_since("09:30") is not None
    assert wr._parse_since("2026-07-13 09:30:00") is not None
    assert wr._parse_since("not-a-time") is None


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items())
           if n.startswith("test_") and callable(g)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
