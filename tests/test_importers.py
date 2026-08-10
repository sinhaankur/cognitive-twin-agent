"""
Location importer tests — Google Timeline parsing + iOS Shortcut incremental
ingest. Both run offline on synthetic files; the Apple/CoreLocation importers need
OS permissions/frameworks so they're only smoke-imported here (they must degrade
honestly, not crash).

Run: python -m pytest tests/test_importers.py -q
     (or: python tests/test_importers.py)
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
    from cognitive_twin import vault, security, places
    importlib.reload(vault)
    importlib.reload(security)
    importlib.reload(places)
    vault._key_cache = None
    return places


def test_google_timeline_all_formats(tmp_path):
    P = _fresh(tmp_path)
    from cognitive_twin.importers import google_timeline as G
    importlib.reload(G)

    folder = tmp_path / "takeout"
    folder.mkdir()
    (folder / "2026_AUGUST.json").write_text(json.dumps({"timelineObjects": [
        {"placeVisit": {"location": {"name": "Equinox Bay St", "latE7": 436470000,
                                     "lngE7": -793810000, "semanticType": "TYPE_GYM"},
                        "duration": {"startTimestamp": "2026-08-09T18:00:00Z",
                                     "endTimestamp": "2026-08-09T19:00:00Z"}}},
        {"activitySegment": {"distance": 900}},  # not a visit → skipped
    ]}))
    (folder / "Timeline.json").write_text(json.dumps({"semanticSegments": [
        {"startTime": "2026-08-10T09:00:00Z", "endTime": "2026-08-10T10:00:00Z",
         "visit": {"topCandidate": {"placeLocation": {"name": "Home",
                                                      "latLng": "43.6532,-79.3832"}}}},
    ]}))
    (folder / "Records.json").write_text(json.dumps({"locations": [
        {"latitudeE7": 436530000, "longitudeE7": -793830000,
         "timestamp": "2026-08-10T12:00:00Z"}]}))

    visits = G.parse(folder)
    names = [v.place for v in visits]
    assert "Equinox Bay St" in names          # semantic
    assert "Home" in names                     # on-device export
    assert any("," in n for n in names)        # raw records → coord-only
    # E7 conversion sanity
    gym = next(v for v in visits if v.place == "Equinox Bay St")
    assert 43 < gym.lat < 44 and -80 < gym.lon < -79
    assert gym.category == "gym"

    P.enable()
    r = G.import_from(folder)
    assert r["imported"] == len(visits)
    # idempotent re-import
    assert G.import_from(folder)["imported"] == 0


def test_google_import_refused_when_disabled(tmp_path):
    P = _fresh(tmp_path)
    from cognitive_twin.importers import google_timeline as G
    importlib.reload(G)
    P.disable()
    f = tmp_path / "x.json"
    f.write_text(json.dumps({"timelineObjects": [
        {"placeVisit": {"location": {"name": "Somewhere", "latE7": 400000000, "lngE7": -700000000},
                        "duration": {"startTimestamp": "2026-08-10T10:00:00Z"}}}]}))
    r = G.import_from(f)
    assert r["imported"] == 0
    assert "off" in r.get("note", "").lower()


def test_ios_shortcut_incremental(tmp_path):
    P = _fresh(tmp_path)
    wf = tmp_path / "places.ndjson"
    os.environ["CTWIN_IOS_PLACES_FILE"] = str(wf)
    from cognitive_twin.importers import ios_shortcut as S
    importlib.reload(S)
    P.enable()

    wf.write_text('{"place":"Gym","lat":43.64,"lon":-79.38,"time":"2026-08-10T18:00:00Z"}\n'
                  '{"place":"Home","time":"2026-08-10T20:00:00Z"}\n')
    assert S.poll()["imported"] == 2
    # append one more; only the new line ingests
    with wf.open("a") as f:
        f.write('{"place":"Cafe","time":"2026-08-10T21:00:00Z"}\n')
    assert S.poll()["imported"] == 1
    assert S.poll()["imported"] == 0        # nothing new
    assert [v.place for v in P.visits_on("2026-08-10")] == ["Gym", "Home", "Cafe"]


def test_apple_and_core_degrade_without_crashing(tmp_path):
    _fresh(tmp_path)
    from cognitive_twin.importers import apple_locations as A, core_location as C
    importlib.reload(A)
    importlib.reload(C)
    # check() must return a dict and never raise, even without Full Disk Access.
    c = A.check()
    assert isinstance(c, dict) and "knowledgeC_readable" in c
    # where() must return a dict with a note if CoreLocation is missing/denied.
    w = C.where()
    assert isinstance(w, dict)
    assert ("lat" in w) or ("note" in w)


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
