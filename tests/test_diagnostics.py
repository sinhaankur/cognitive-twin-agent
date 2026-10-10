"""Diagnostics must never crash a run, must shape its report + log correctly, and
`trends()` must compute reliability from history. Network checks degrade to ✗
lines offline (no brain in CI), which is itself the point — the report survives
anything."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from cognitive_twin import diagnostics as D


def test_run_never_raises_and_has_sections():
    # With no brain reachable, the core network checks fail gracefully — the
    # report still builds and renders.
    rep = D.run(log=False)
    assert set(rep.sections) == {"core", "subsystems", "security", "performance"}
    text = rep.render()
    assert "Vera diagnostics" in text
    d = rep.as_dict()
    assert "ok" in d and "sections" in d


def test_log_line_has_tracked_keys():
    rep = D.run(log=False)
    line = rep.log_line()
    for k in ("ts", "ok", "brain_ok", "llm_ok", "voice_ok", "mic_ok", "opener_ok", "failures"):
        assert k in line
    # round-trips as JSON (it's what we append to the log)
    assert json.loads(json.dumps(line))["ts"] == line["ts"]


def test_trends_reads_history(monkeypatch):
    # point the log at a temp file seeded with a flaky-mic history
    tmp = Path(tempfile.mkdtemp()) / "diag.jsonl"
    rows = [
        {"ts": "2026-10-10T10:00:00", "ok": True,  "brain_ok": True, "llm_ok": True,
         "voice_ok": True, "mic_ok": True,  "opener_ok": True, "failures": []},
        {"ts": "2026-10-10T11:00:00", "ok": False, "brain_ok": True, "llm_ok": True,
         "voice_ok": True, "mic_ok": False, "opener_ok": True, "failures": ["mic/transcribe pipeline"]},
        {"ts": "2026-10-10T12:00:00", "ok": True,  "brain_ok": True, "llm_ok": True,
         "voice_ok": True, "mic_ok": True,  "opener_ok": True, "failures": []},
    ]
    tmp.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(D, "_LOG", tmp)

    out = D.trends(14)
    assert "mic" in out
    assert "2/3 ok" in out            # mic failed 1 of 3 → flaky
    assert "FLAKY" in out
    assert "most frequent failures" in out


def test_tone_wav_is_valid_riff():
    wav = D._tone_wav(seconds=0.1)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    assert len(wav) > 44   # header + some samples
