"""
Life-story tests — the lived past that makes the twin *them*. Sealed at rest,
honest when empty, never invents, compiles into the system prompt. Isolated to a
temp memory dir; no model required.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fresh():
    d = tempfile.mkdtemp()
    os.environ["CTWIN_MEMORY_DIR"] = d
    os.environ["CTWIN_PERSONA_DIR"] = d
    os.environ["CTWIN_NO_UNHOSTED"] = "1"
    import cognitive_twin.security as security
    import cognitive_twin.life_story as life_story
    for m in (security, life_story):
        importlib.reload(m)
    return life_story, Path(d)


def test_empty_is_silent_and_honest():
    ls, _ = _fresh()
    assert ls.load().is_empty() is True
    assert ls.to_prompt() == ""          # no invented past
    assert "not set" in ls.status()
    print("✓ empty life story → silent (no fabricated past)")


def test_builds_and_compiles_into_prompt():
    ls, _ = _fresh()
    ls.add_person("Ankur", "son", "the one who built this")
    ls.add_place("Munger, where I grew up")
    ls.add_saying("Beta, have you eaten?")
    ls.add_love("making chai at dawn")
    ls.add_date("married 1974")
    ls.add_story("Sunday mornings", "We'd all be in the kitchen before anyone was properly awake.", "when the kids were small")

    block = ls.to_prompt()
    assert "Ankur" in block and "son" in block
    assert "Munger" in block
    assert "Beta, have you eaten?" in block     # her actual saying surfaces
    assert "chai" in block
    assert "married 1974" in block
    assert "Sunday mornings" in block
    # the honesty instruction must be present so the model won't invent beyond it
    assert "invent" in block.lower()
    print("✓ life story compiles people/places/sayings/loves/dates/stories into the prompt")


def test_sealed_at_rest():
    ls, d = _fresh()
    ls.add_saying("Beta, have you eaten?")
    raw = (d / "life_story.json").read_bytes()
    # sealed → the plaintext saying must NOT appear on disk
    assert b"have you eaten" not in raw
    try:
        json.loads(raw.decode("utf-8"))
        sealed = False   # if it parses as our plaintext JSON with the saying, it'd be a leak
    except Exception:
        sealed = True
    assert sealed or b"have you eaten" not in raw
    # but it reads back correctly through the kernel
    assert "Beta, have you eaten?" in ls.load().sayings
    print("✓ life story is sealed at rest, reads back through the kernel")


def test_dedupes_and_survives_reload():
    ls, _ = _fresh()
    ls.add_saying("one line")
    ls.add_saying("one line")           # duplicate ignored
    ls.add_place("home")
    assert ls.load().sayings.count("one line") == 1
    importlib.reload(ls)
    assert "one line" in ls.load().sayings
    assert "home" in ls.load().places
    print("✓ dedupes repeats and survives a reload")


def test_moment_hint_only_with_sayings_and_never_invents():
    ls, _ = _fresh()
    # No sayings yet → no hint (never fabricates her voice)
    assert ls.moment_hint("heavy") == ""
    assert ls.moment_hint("bright") == ""
    ls.add_saying("Beta, have you eaten?")
    heavy = ls.moment_hint("heavy")
    bright = ls.moment_hint("bright")
    assert "Beta, have you eaten?" in heavy
    assert "tender moment" in heavy          # moment-aware nudge
    assert "warm moment" in bright
    # the guard rails are always present
    for h in (heavy, bright):
        assert "at most one" in h
        assert "never force" in h.lower() or "never invent" in h.lower()
    print("✓ moment hint: only with real sayings, moment-aware, never invents")


if __name__ == "__main__":
    test_empty_is_silent_and_honest()
    test_builds_and_compiles_into_prompt()
    test_sealed_at_rest()
    test_dedupes_and_survives_reload()
    test_moment_hint_only_with_sayings_and_never_invents()
    print("\nall life-story tests passed")
