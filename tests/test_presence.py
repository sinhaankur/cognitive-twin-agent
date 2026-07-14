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


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items())
           if n.startswith("test_") and callable(g)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
