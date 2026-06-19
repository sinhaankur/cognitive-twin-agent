"""
Tests for the personal-layer modules: soul (evolving personality + reflections),
rhythms (timezone + sleep/work awareness), and voice_profile (speaking in a loved
one's voice from their writing + custom memory).

All offline, isolated temp dirs — never touches the real ~/.cognitive-twin, never
needs a live model or cloning engine.

Run: python tests/test_soul_rhythms_voice.py
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Isolate ALL on-device state to a throwaway dir before importing the modules.
_TMP = tempfile.mkdtemp()
os.environ["CTWIN_MEMORY_DIR"] = _TMP
os.environ["CTWIN_PERSONA_DIR"] = _TMP

from cognitive_twin import memory as M          # noqa: E402
from cognitive_twin import soul as S            # noqa: E402
from cognitive_twin import rhythms as R         # noqa: E402
from cognitive_twin import voice_profile as VP  # noqa: E402


def _seed_memory(hours, prompt="work on the rust core"):
    """Write interaction entries at given hours so rhythms/soul have data."""
    path = Path(_TMP) / "memory.jsonl"
    with path.open("w") as f:
        for h in hours:
            ts = datetime.datetime.now().replace(hour=h, minute=0).isoformat()
            f.write(json.dumps({"ts": ts, "prompt": prompt, "gist": "x"}) + "\n")


# ---------- soul ----------
def test_soul_evolves_with_interactions():
    M.clear(); S.clear()
    _seed_memory([9, 10, 14], prompt="thank you so much, I love this")
    soul = S.evolve_personality()
    assert soul["interactions"] == 3
    assert soul["tone"] in ("warm and caring", "practical and focused")
    assert "familiarity" in soul
    assert S.personality_prompt().startswith("# WHO YOU'VE BECOME")
    print("✓ soul: evolves familiarity + tone from interactions")


def test_soul_reflections_store_and_clear():
    M.clear(); S.clear()
    S.add_reflection("Maybe cache the model list.")
    items = S.pending_reflections()
    assert len(items) == 1 and "cache" in items[0]["thought"]
    S.clear()
    assert S.pending_reflections() == []
    print("✓ soul: reflections store + clear")


def test_soul_empty_is_quiet():
    M.clear(); S.clear()
    assert S.personality_prompt() == ""   # nothing learned yet → no block
    print("✓ soul: silent until there's history")


# ---------- rhythms ----------
def test_rhythms_timezone_always_explicit():
    line = R.timezone_line()
    assert "UTC" in line and "Always use this timezone" in line
    print("✓ rhythms: timezone line is explicit")


def test_rhythms_infers_sleep_and_work():
    M.clear()
    # active 9-17 + a couple late; quietest block should be overnight
    _seed_memory([9, 10, 11, 13, 14, 15, 16, 17, 22])
    r = R.infer()
    assert r["interactions"] >= 8
    assert "likely_work" in r
    assert r["likely_work"]["from"] >= 8 and r["likely_work"]["to"] <= 18
    assert "YOUR DAY" in R.summary_for_prompt()
    print("✓ rhythms: infers work window + builds prompt block")


def test_rhythms_override_wins():
    M.clear()
    R.set_override("sleep", "23:30")
    assert R.infer().get("sleep") == "23:30"
    print("✓ rhythms: user-stated override is kept")


def test_part_of_day():
    assert R.part_of_day() in {"late night", "morning", "afternoon", "evening", "night"}
    print("✓ rhythms: part_of_day is sane")


# ---------- voice_profile (speak like a loved one) ----------
def test_voice_profile_learns_signature_phrases():
    VP.clear_voice()
    VP.add_samples(
        "Good morning beta, did you eat?\n"
        "So proud of you my boy, take care\n"
        "Love you, god bless",
        person="Mom")
    block = VP.voice_prompt()
    assert "Mom" in block
    assert "beta" in block.lower()
    assert "examples of how they actually wrote" in block.lower()
    print("✓ voice_profile: learns voice + signature phrases")


def test_voice_profile_empty_is_quiet():
    VP.clear_voice()
    assert VP.voice_prompt() == ""
    print("✓ voice_profile: silent with no samples")


def test_custom_memory_remember_and_compile():
    # custom memory lives in voice_profile
    facts_before = len(VP.custom_facts())
    VP.remember("My daughter's recital is on Friday.")
    assert "recital" in " ".join(VP.custom_facts())
    assert "WHAT YOU KNOW" in VP.custom_prompt()
    # idempotent: same fact not duplicated
    n = VP.remember("My daughter's recital is on Friday.")
    assert n == len(VP.custom_facts())
    print("✓ custom memory: remember + compile + no duplicates")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nall soul/rhythms/voice tests passed.")
