"""
Social (Meta) tests — sentiment scorer, sealed index gates, Meta export parsing.

All offline on synthetic files. Asserts: sentiment sign/negation, intake refused
when disabled, sealed at rest, the four signals compute, and the Meta importer
parses FB/IG posts+comments with on-device sentiment.

Run: python -m pytest tests/test_social.py -q  (or: python tests/test_social.py)
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fresh(tmp: Path):
    os.environ["CTWIN_MEMORY_DIR"] = str(tmp)
    from cognitive_twin import vault, security, social
    importlib.reload(vault)
    importlib.reload(security)
    importlib.reload(social)
    vault._key_cache = None
    return social


def test_sentiment_sign_and_negation():
    from cognitive_twin.importers.sentiment import score
    assert score("I love this, so happy!") > 0.5
    assert score("worst day, so tired and sad") < -0.5
    assert score("not good") < 0                     # negation flips
    assert score("the meeting is at 3pm") == 0.0     # neutral / no signal


def test_intake_refused_when_disabled(tmp_path):
    S = _fresh(tmp_path)
    S.disable()
    from cognitive_twin.social import Activity
    assert S.import_activities([Activity("facebook", "post", 1.0, "hi")]) == 0
    assert S.read_all() == []


def test_sealed_and_signals(tmp_path):
    S = _fresh(tmp_path)
    S.enable()
    from cognitive_twin.social import Activity
    import time
    now = time.time()
    S.import_activities([
        Activity("facebook", "post", now - 86400, "so happy and grateful", sentiment=0.8),
        Activity("instagram", "post", now - 2 * 86400, "beautiful", target="", sentiment=0.6),
        Activity("facebook", "comment", now - 3 * 86400, "love it", target="Alex", sentiment=0.9),
    ])
    raw = S._log_path().read_bytes()
    assert b"grateful" not in raw                     # sealed
    a = S.activity_over_time(3650)
    assert a["total"] == 3 and a["by_platform"]["facebook"] == 2
    s = S.sentiment_trend(3650)
    assert s["count"] == 3 and s["avg"] > 0
    assert S.top_interactions(3650)[0][0] == "Alex"


def test_meta_export_parse(tmp_path):
    S = _fresh(tmp_path)
    S.enable()
    from cognitive_twin.importers import meta_export as M
    importlib.reload(M)

    exp = tmp_path / "meta"
    (exp / "posts").mkdir(parents=True)
    (exp / "posts" / "your_posts_1.json").write_text(json.dumps([
        {"timestamp": 1723219200, "data": [{"post": "amazing day, so happy!"}]},
        {"timestamp": 1720627200, "data": [{"post": "worst week, so stressed"}]},
    ]))
    (exp / "comments_1.json").write_text(json.dumps({"comments_v2": [
        {"timestamp": 1723000000, "title": "commented on Alex's post",
         "data": [{"comment": {"comment": "love this"}}]}]}))
    (exp / "instagram_posts_1.json").write_text(json.dumps([
        {"media": [{"creation_timestamp": 1722000000, "title": "sunset"}]}]))

    acts = M.parse(exp)
    kinds = {(a.platform, a.kind) for a in acts}
    assert ("facebook", "post") in kinds
    assert ("facebook", "comment") in kinds
    assert ("instagram", "post") in kinds
    # sentiment scored on the ones with text
    happy = next(a for a in acts if "happy" in a.text)
    assert happy.sentiment is not None and happy.sentiment > 0

    r = M.import_from(exp)
    assert r["imported"] == len(acts)
    assert M.import_from(exp)["imported"] == 0        # idempotent


if __name__ == "__main__":
    import tempfile, inspect

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            needs_tmp = "tmp_path" in inspect.signature(fn).parameters
            if needs_tmp:
                with tempfile.TemporaryDirectory() as d:
                    try:
                        fn(Path(d)); print(f"  ✓ {name}")
                    except AssertionError as e:
                        failures += 1; print(f"  ✗ {name}: {e}")
            else:
                try:
                    fn(); print(f"  ✓ {name}")
                except AssertionError as e:
                    failures += 1; print(f"  ✗ {name}: {e}")
    print("OK" if not failures else f"{failures} FAILED")
    sys.exit(1 if failures else 0)
