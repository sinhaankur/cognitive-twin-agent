"""
Presence tests — the opt-in camera sense is ephemeral and honest: only derived
motion facts, only the latest reading, gone when stale or stopped, and the
prompt line never claims emotions. Pure module, no camera needed.

Run: python -m pytest tests/ -q   (or: python tests/test_presence.py)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cognitive_twin import presence


def test_off_by_default_and_empty_context():
    presence.stop()
    assert presence.current() is None
    assert presence.context_for_prompt() == ""


def test_update_then_context_reports_motion_facts_only():
    presence.update({"present": True, "energy": 0.4, "gesture": "nod", "lean": "in"})
    c = presence.current()
    assert c and c["present"] and c["gesture"] == "nod"
    line = presence.context_for_prompt()
    assert "animated" in line and "nodded" in line and "leaning in" in line
    # the honesty clause travels with every reading
    assert "never claim" in line
    presence.stop()


def test_sanitizes_junk_input():
    presence.update({"present": 1, "energy": 99, "gesture": "angry", "lean": "sideways"})
    c = presence.current()
    assert c["energy"] == 1.0          # clamped
    assert c["gesture"] is None        # unknown gestures dropped, not invented
    assert c["lean"] is None
    presence.stop()


def test_stale_reading_is_forgotten():
    presence.update({"present": True, "energy": 0.2})
    presence._last["ts"] = time.time() - 60          # age it past the window
    assert presence.current() is None
    assert presence.context_for_prompt() == ""
    presence.stop()


def test_stop_forgets_immediately():
    presence.update({"present": True, "energy": 0.2})
    presence.stop()
    assert presence.current() is None





# ---- the ear: ambient sound (opt-in, ephemeral, honest) -----------------------

def test_ambient_reports_sound_types():
    presence.update_ambient({"sounds": [{"label": "music", "conf": 0.8},
                                        {"label": "typing", "conf": 0.5}],
                             "loud": 0.3})
    ctx = presence.context_for_prompt()
    assert "music" in ctx and "typing" in ctx
    assert "lively" in ctx
    assert "never recordings" in ctx
    presence.stop_ambient()


def test_ambient_drops_low_confidence_and_junk():
    presence.update_ambient({"sounds": [{"label": "dog", "conf": 0.2},
                                        {"label": "", "conf": 0.9}],
                             "loud": 0.05})
    amb = presence.ambient_current()
    assert amb is not None and amb["sounds"] == []
    assert presence.context_for_prompt() == ""     # quiet + nothing confident
    presence.stop_ambient()


def test_ambient_stale_and_stop_forget():
    presence.update_ambient({"sounds": [{"label": "music", "conf": 0.9}], "loud": 0.5})
    presence._ambient["ts"] = time.time() - 60
    assert presence.ambient_current() is None
    presence.update_ambient({"sounds": [{"label": "music", "conf": 0.9}], "loud": 0.5})
    presence.stop_ambient()
    assert presence.ambient_current() is None


def test_face_and_ear_compose():
    presence.update({"present": True, "energy": 0.2})
    presence.update_ambient({"sounds": [{"label": "music", "conf": 0.9}], "loud": 0.5})
    ctx = presence.context_for_prompt()
    assert "calm" in ctx and "music" in ctx
    presence.stop(); presence.stop_ambient()


def test_room_solo_with_you():
    presence.update({"present": True, "energy": 0.3, "source": "face",
                     "people": 1, "people_attending": 1, "addressing_her": True})
    ctx = presence.context_for_prompt()
    assert "just the two of you" in ctx
    presence.stop()


def test_room_group_chatter_tells_her_to_hold_back():
    """The whole point: in a group where no one's looking at her, she should be
    told this is likely not meant for her — so she doesn't jump into chatter."""
    presence.update({"present": True, "energy": 0.5, "source": "face",
                     "people": 3, "people_attending": 0, "addressing_her": False})
    ctx = presence.context_for_prompt()
    assert "3 people" in ctx
    assert "not to you" in ctx and ("Stay quiet" in ctx or "unless" in ctx)
    presence.stop()


def test_room_group_someone_addressing_her():
    presence.update({"present": True, "energy": 0.4, "source": "face",
                     "people": 2, "people_attending": 1, "addressing_her": True})
    ctx = presence.context_for_prompt()
    assert "2 people" in ctx and "looking toward you" in ctx
    presence.stop()


def test_room_fields_ignored_when_absent():
    """No room data (e.g. browser optical-flow eye) → no room line, no crash."""
    presence.update({"present": True, "energy": 0.2, "source": "flow"})
    ctx = presence.context_for_prompt()
    assert "people here" not in ctx and "two of you" not in ctx
    presence.stop()


# ---- the device sense: the ecosystem around the moment (opt-in, EPHEMERAL) ----
# Reactive-only: it tells her when to hold back; it never makes her speak. Stores
# nothing. We patch the probes so no real app/mic is needed.

def _patch_probes(monkeypatch, app="", title="", mic=None, music=False):
    monkeypatch.setattr(presence, "_frontmost", lambda: (app, title))
    monkeypatch.setattr(presence, "mic_active", lambda: mic)
    monkeypatch.setattr(presence, "_music_playing", lambda: music)


def test_device_off_by_default_is_neutral():
    presence.disable_device()
    assert presence.device_enabled() is False
    d = presence.device_now()
    assert d["activity"] == "unknown" and d["should_interject"] is True
    assert presence._device_context() == ""        # silent when off


def test_device_meeting_app_with_mic_holds_back(monkeypatch):
    presence.enable_device()
    _patch_probes(monkeypatch, app="zoom.us", title="Zoom Meeting", mic=True)
    d = presence.device_now()
    assert d["activity"] == "meeting" and d["should_interject"] is False
    assert d["confidence"] >= 0.9
    line = presence._device_context()
    assert "call or meeting" in line and "very short" in line
    presence.disable_device()


def test_device_meeting_in_browser_tab(monkeypatch):
    presence.enable_device()
    _patch_probes(monkeypatch, app="Google Chrome",
                  title="Standup - meet.google.com - Google Chrome", mic=True)
    d = presence.device_now()
    assert d["activity"] == "meeting" and d["should_interject"] is False
    presence.disable_device()


def test_device_video_keeps_it_brief(monkeypatch):
    presence.enable_device()
    _patch_probes(monkeypatch, app="Safari", title="Lofi mix - YouTube", mic=False)
    d = presence.device_now()
    assert d["activity"] == "video" and d["should_interject"] is True
    assert "brief" in presence._device_context()
    presence.disable_device()


def test_device_music_is_ambient_not_holding_back(monkeypatch):
    presence.enable_device()
    _patch_probes(monkeypatch, app="Notes", title="", mic=False, music=True)
    d = presence.device_now()
    assert d["activity"] == "music" and d["should_interject"] is True
    assert presence._device_context() == ""        # music doesn't change her replies
    presence.disable_device()


def test_device_plain_work_does_not_interrupt_replies(monkeypatch):
    presence.enable_device()
    _patch_probes(monkeypatch, app="Xcode", title="main.swift", mic=False)
    d = presence.device_now()
    assert d["activity"] == "work" and d["should_interject"] is True
    assert presence._device_context() == ""
    presence.disable_device()


def test_device_mic_live_alone_is_a_call(monkeypatch):
    presence.enable_device()
    _patch_probes(monkeypatch, app="Terminal", title="", mic=True)
    d = presence.device_now()
    assert d["activity"] == "call" and d["should_interject"] is False
    presence.disable_device()


def test_device_sense_stores_nothing(monkeypatch, tmp_path):
    """The whole privacy promise: reading the device NEVER writes a file."""
    import os
    monkeypatch.setenv("CTWIN_MEMORY_DIR", str(tmp_path))
    presence.enable_device()                          # this writes ONLY the on-flag
    _patch_probes(monkeypatch, app="zoom.us", title="", mic=True)
    presence.device_now()
    presence.device_now()
    presence._device_context()
    files = sorted(os.listdir(tmp_path))
    # the only thing that may exist is the enable flag — never an activity log/state
    assert "presence.jsonl" not in files
    assert "presence_state.json" not in files
    assert all(not f.endswith(".jsonl") for f in files)
    presence.disable_device()


def test_device_context_flows_through_main_context(monkeypatch):
    """context_for_prompt() composes the device line alongside camera/ear."""
    presence.enable_device()
    _patch_probes(monkeypatch, app="zoom.us", title="Zoom Meeting", mic=True)
    ctx = presence.context_for_prompt()
    assert "call or meeting" in ctx
    presence.disable_device()


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items())
           if n.startswith("test_") and callable(g)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
