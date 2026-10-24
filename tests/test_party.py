"""party mode (BTK10 laser) — opt-in gate + the safety contract.

The one thing that MUST hold: it's off by default, and lights_off restores the
audio output we saved on lights_on (sound never stays trapped in a light). We
stub the local CLIs so the test never touches real Bluetooth/audio.
"""

from __future__ import annotations

from cognitive_twin import party


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("CTWIN_PARTY", raising=False)
    assert party.is_enabled() is False
    # inert when off — lights_on refuses without touching anything
    msg = party.lights_on()
    assert "off" in msg.lower() and "opt-in" in msg.lower()


def test_enable_toggle(monkeypatch):
    monkeypatch.delenv("CTWIN_PARTY", raising=False)
    party.enable(True);  assert party.is_enabled() is True
    party.enable(False); assert party.is_enabled() is False


def test_missing_tools_explains(monkeypatch):
    monkeypatch.setenv("CTWIN_PARTY", "1")
    monkeypatch.setattr(party, "_tool", lambda name: None)   # no CLIs installed
    msg = party.lights_on()
    assert "brew install" in msg


def test_lights_on_saves_and_off_restores(tmp_path, monkeypatch):
    monkeypatch.setenv("CTWIN_PARTY", "1")
    monkeypatch.setenv("CTWIN_MEMORY_DIR", str(tmp_path))   # sealed note isolated
    # pretend both tools exist and the laser is reachable
    monkeypatch.setattr(party, "_tool", lambda name: "/usr/local/bin/" + name)
    monkeypatch.setattr(party, "_connect_laser", lambda: True)
    monkeypatch.setattr(party, "_laser_connected", lambda: True)
    monkeypatch.setattr(party, "_play_music", lambda: "music started")

    # a mutable fake "current output" the stubbed setter drives
    state = {"out": "MacBook Pro Speakers"}
    monkeypatch.setattr(party, "_current_output", lambda: state["out"])
    def _set(dev):
        state["out"] = dev
        return True
    monkeypatch.setattr(party, "_set_output", _set)
    monkeypatch.setattr(party, "_pause_music", lambda: None)

    on = party.lights_on(music=True)
    assert party.LASER_NAME in on
    assert state["out"] == party.LASER_NAME        # audio routed to the laser

    off = party.lights_off()
    assert state["out"] == "MacBook Pro Speakers"  # restored the saved output
    assert "back on MacBook Pro Speakers" in off


def test_lights_off_defaults_safely_when_no_saved(tmp_path, monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", str(tmp_path))
    monkeypatch.setattr(party, "_tool", lambda name: "/usr/local/bin/" + name)
    state = {"out": party.LASER_NAME}
    monkeypatch.setattr(party, "_current_output", lambda: state["out"])
    monkeypatch.setattr(party, "_set_output", lambda dev: state.__setitem__("out", dev) or True)
    monkeypatch.setattr(party, "_pause_music", lambda: None)
    # no prior saved → falls back to the Mac speakers, never leaves it on the laser
    party.lights_off()
    assert state["out"] == "MacBook Pro Speakers"
