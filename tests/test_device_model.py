"""
Device-model tests — pick the RIGHT-SIZED model for the machine, so install stays
light. The key promise: a small Mac never gets told to pull a model too big for it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cognitive_twin import device_model as d


def test_recommend_pull_scales_with_ram():
    # small machine → a light 3B/1.5B, NEVER the 7B
    small = d.recommend_pull(ram_gb=8)
    assert "7b" not in small and "14b" not in small
    tiny = d.recommend_pull(ram_gb=4)
    assert "7b" not in tiny and "14b" not in tiny
    # roomy machine → her trained voice (a light 3B), preferred
    for ram in (16, 32, 64):
        assert d.recommend_pull(ram_gb=ram) == "vera-tuned"
    print("✓ recommend_pull scales with RAM — small Macs stay light, never a 7B")


def test_recommend_pull_is_always_a_real_candidate():
    for ram in (2, 8, 12, 16, 48):
        m = d.recommend_pull(ram_gb=ram)
        assert isinstance(m, str) and m
        # it's one of the known light options
        assert m in ("vera-tuned", "qwen2.5:3b", "qwen2.5:1.5b")
    print("✓ recommend_pull always returns a real, light model id")


def test_runtime_pick_still_prefers_installed_vera():
    # when vera-tuned is installed, the runtime picker uses it regardless of tier
    pick = d.pick_default(installed=["vera-tuned", "qwen2.5:7b"], ram_gb=64)
    assert pick == "vera-tuned"
    print("✓ runtime picker still prefers her trained model when installed")


if __name__ == "__main__":
    test_recommend_pull_scales_with_ram()
    test_recommend_pull_is_always_a_real_candidate()
    test_runtime_pick_still_prefers_installed_vera()
    print("\nall device-model tests passed")
