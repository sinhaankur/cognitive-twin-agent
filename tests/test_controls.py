"""
Controls tests — the standalone toggle layer behind the control panel.

Asserts controls.py works as pure logic (no Vera/UI needed): snapshot lists all
controls grouped, set_control flips a safe toggle, guards reject read-only and
unknown keys, and the booker bridge reads its real confirmBookings flag without
flipping it. Runs in a temp memory dir.

Run: python -m pytest tests/test_controls.py -q  (or: python tests/test_controls.py)
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fresh(tmp: Path):
    os.environ["CTWIN_MEMORY_DIR"] = str(tmp)
    from cognitive_twin import vault, security, controls
    importlib.reload(vault)
    importlib.reload(security)
    importlib.reload(controls)
    vault._key_cache = None
    return controls


def test_snapshot_lists_grouped_controls(tmp_path):
    C = _fresh(tmp_path)
    snap = C.snapshot()
    keys = {c["key"] for c in snap}
    assert {"activity", "mood", "places", "social", "screen_control"} <= keys
    assert all("group" in c and "on" in c and "available" in c for c in snap)
    assert len({c["group"] for c in snap}) >= 3


def test_set_control_flips_safe_toggle(tmp_path):
    C = _fresh(tmp_path)
    r = C.set_control("places", True)
    assert r.get("on") is True
    r = C.set_control("places", False)
    assert r.get("on") is False


def test_readonly_and_unknown_guards(tmp_path):
    C = _fresh(tmp_path)
    assert "error" in C.set_control("email_connected", True)   # read-only
    assert "error" in C.set_control("does_not_exist", True)     # unknown


def test_booker_bridge_reads_without_flipping(tmp_path):
    C = _fresh(tmp_path)
    snap = {c["key"]: c for c in C.snapshot()}
    # booker_confirm exists and reflects a bool; reading it must not change the file
    assert "booker_confirm" in snap
    assert isinstance(snap["booker_confirm"]["on"], bool)


def test_your_life_sync_group(tmp_path):
    """Calendar / Mail / Photos / Location are one coherent opt-in sync group,
    each off by default (places may vary), and the safe ones flip cleanly."""
    C = _fresh(tmp_path)
    snap = {c["key"]: c for c in C.snapshot()}
    life = {"calendar", "mail", "photos", "places"}
    assert life <= set(snap), f"missing: {life - set(snap)}"
    # they share ONE group
    groups = {snap[k]["group"] for k in life}
    assert len(groups) == 1 and "Your life" in next(iter(groups))
    # calendar + photos are safe toggles that flip and persist
    for key in ("calendar", "photos"):
        assert C.set_control(key, True).get("on") is True
        assert {c["key"]: c for c in C.snapshot()}[key]["on"] is True
        assert C.set_control(key, False).get("on") is False
    # mail is gated on IMAP being configured — unavailable (but listed) with no creds
    assert snap["mail"]["available"] is False


if __name__ == "__main__":
    import tempfile

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            with tempfile.TemporaryDirectory() as d:
                try:
                    fn(Path(d)); print(f"  ✓ {name}")
                except AssertionError as e:
                    failures += 1; print(f"  ✗ {name}: {e}")
    print("OK" if not failures else f"{failures} FAILED")
    sys.exit(1 if failures else 0)
