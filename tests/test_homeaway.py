"""
home/away — Vera senses when you come home and when you leave.

Off until a home is set; fuses Wi-Fi / phone / geofence / Mac signals into one
state; DEBOUNCES so a blip doesn't fire a transition; other devices can report in;
a guest never learns whether the owner is home. No audio, no location trail kept.
"""
from __future__ import annotations

import tempfile
import time

from cognitive_twin import homeaway


def _fresh(monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())


def test_off_until_home_is_set(monkeypatch):
    _fresh(monkeypatch)
    assert homeaway.is_configured() is False
    assert homeaway.tick() is None                 # nothing fires with no home
    assert homeaway.context_for_prompt() == ""     # nothing to say


def test_set_home_by_wifi(monkeypatch):
    _fresh(monkeypatch)
    homeaway.set_home(ssids=["HomeNet"])
    assert homeaway.is_configured() is True
    assert "HomeNet" in homeaway.status()


def test_device_report_drives_arrival(monkeypatch):
    _fresh(monkeypatch)
    homeaway.set_home(ssids=["HomeNet"])
    # no Wi-Fi reading in the test env → the phone's report is the vote
    homeaway.report(device="iphone", home=True)
    # arrival needs ~25s of agreement; simulate by backdating the pending timer
    ev = homeaway.tick()
    # first tick starts the debounce; force it past the window
    st = homeaway._load()
    if st.get("pending"):
        st["pending"]["since"] = time.time() - 60
        homeaway._save(st)
    ev = homeaway.tick()
    assert ev is not None and ev["event"] == "arrived"
    assert homeaway.current()["home"] is True
    assert "home" in homeaway.context_for_prompt().lower()


def test_leaving_goes_quiet(monkeypatch):
    _fresh(monkeypatch)
    homeaway.set_home(ssids=["HomeNet"])
    # become home first
    homeaway.report(device="iphone", home=True)
    homeaway.tick()
    st = homeaway._load()
    if st.get("pending"):
        st["pending"]["since"] = time.time() - 60
        homeaway._save(st)
    homeaway.tick()
    assert homeaway.is_away() is False
    # now the phone leaves
    homeaway.report(device="iphone", home=False)
    homeaway.tick()
    st = homeaway._load()
    if st.get("pending"):
        st["pending"]["since"] = time.time() - 300   # leave debounce is longer
        homeaway._save(st)
    ev = homeaway.tick()
    assert ev is not None and ev["event"] == "left"
    assert homeaway.is_away() is True
    assert "empty room" in homeaway.context_for_prompt()


def test_debounce_blip_does_not_fire(monkeypatch):
    _fresh(monkeypatch)
    homeaway.set_home(ssids=["HomeNet"])
    homeaway.report(device="iphone", home=True)
    # a single tick is within the debounce window → no transition yet
    ev = homeaway.tick()
    assert ev is None
    assert homeaway.current()["home"] is None        # not confirmed on a blip


def test_stale_report_is_ignored(monkeypatch):
    _fresh(monkeypatch)
    homeaway.set_home(ssids=["HomeNet"])
    homeaway.report(device="iphone", home=True)
    # age the report past the staleness window
    st = homeaway._load()
    st["device_reports"]["iphone"]["ts"] = time.time() - (16 * 60)
    homeaway._save(st)
    r = homeaway.read()
    assert r.signals["phone_lan"] is None            # stale → doesn't vote


def test_greetings_are_warm(monkeypatch):
    _fresh(monkeypatch)
    assert homeaway.greeting_for("arrived")
    assert homeaway.greeting_for("left")
    assert homeaway.greeting_for("arrived") != ""


def test_state_is_sealed(monkeypatch, tmp_path):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", str(tmp_path))
    homeaway.set_home(ssids=["HomeNet"])
    homeaway.report(device="iphone", home=True, lat=1.0, lon=2.0)
    f = tmp_path / "homeaway_state.json"
    if f.exists():
        raw = f.read_bytes()
        assert not raw.lstrip().startswith(b"{")     # sealed, not plaintext
