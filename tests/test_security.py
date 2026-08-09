"""
Security kernel tests — the guarantee that everything personal is sealed at rest.

These assert the promises Vera makes: (1) state + log writes are noise on disk,
(2) reads round-trip through the kernel, (3) legacy plaintext is accepted and
re-sealed without data loss, (4) the audit flags plaintext and passes once sealed,
(5) files are owner-only. Each test runs in its own temp CTWIN_MEMORY_DIR so it
never touches your real ~/.cognitive-twin.

Run: python -m pytest tests/ -q   (or: python tests/test_security.py)
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fresh_modules(tmp: Path):
    """Import security+vault bound to a temp memory dir (fresh key cache)."""
    os.environ["CTWIN_MEMORY_DIR"] = str(tmp)
    from cognitive_twin import vault, security
    importlib.reload(vault)
    importlib.reload(security)
    vault._key_cache = None  # force re-derive under this env
    return vault, security


def test_state_is_noise_at_rest_and_round_trips(tmp_path):
    vault, S = _fresh_modules(tmp_path)
    p = S.path("soul.json")
    S.write_state(p, {"tone": "warm", "shared": ["mars", "silkworms"]})
    raw = p.read_bytes()
    assert vault.is_sealed_bytes(raw)
    assert b"warm" not in raw and b"silkworms" not in raw  # noise at rest
    assert S.read_state(p) == {"tone": "warm", "shared": ["mars", "silkworms"]}


def test_log_lines_sealed_and_round_trip(tmp_path):
    vault, S = _fresh_modules(tmp_path)
    p = S.path("places.jsonl")
    S.append_line(p, {"place": "Home", "start": "2026-08-09T08:00"})
    S.append_line(p, {"place": "Gym", "start": "2026-08-09T10:00"})
    raw = p.read_text()
    assert "Home" not in raw and "Gym" not in raw  # every line is sealed
    got = S.read_lines(p)
    assert [r["place"] for r in got] == ["Home", "Gym"]


def test_legacy_plaintext_is_readable_then_resealed(tmp_path):
    vault, S = _fresh_modules(tmp_path)
    p = S.path("mood.json")
    p.write_text(json.dumps({"reflective": True}), encoding="utf-8")  # legacy plaintext
    assert S.read_state(p) == {"reflective": True}          # accepted as-is
    S.write_state(p, S.read_state(p))                        # next write re-seals
    assert vault.is_sealed_bytes(p.read_bytes())


def test_audit_flags_plaintext_then_passes_after_seal_all(tmp_path):
    vault, S = _fresh_modules(tmp_path)
    S.path("mood.json").write_text(json.dumps({"reflective": False}), encoding="utf-8")
    with S.path("activity.jsonl").open("w") as f:
        f.write(json.dumps({"app": "Safari"}) + "\n")
    before = dict(S.audit())
    assert "PLAINTEXT" in before["mood.json"]
    assert "PLAINTEXT" in before["activity.jsonl"]

    result = S.seal_all()
    assert result["state_files_sealed"] >= 1
    assert result["log_lines_sealed"] >= 1

    after = dict(S.audit())
    assert after["mood.json"] == "sealed"
    assert after["activity.jsonl"] == "sealed"
    # data survived the migration
    assert S.read_state(S.path("mood.json")) == {"reflective": False}


def test_files_are_owner_only(tmp_path):
    vault, S = _fresh_modules(tmp_path)
    p = S.path("rhythms.json")
    S.write_state(p, {"likely_sleep": {"from": 23, "to": 7}})
    mode = p.stat().st_mode & 0o777
    assert mode & 0o077 == 0, f"expected owner-only, got {oct(mode)}"


def test_read_state_default_when_absent(tmp_path):
    vault, S = _fresh_modules(tmp_path)
    assert S.read_state(S.path("nope.json"), default={"x": 1}) == {"x": 1}


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
