"""
google_timeline — import your own Google location history into Vera's places index.

Google moved Timeline on-device, so the private way to get your history is a file
*you* download — either a **Takeout** export (Location History) or the **on-device
Timeline export** from the phone. You point Vera at that file/folder and it parses
the *place visits* (named stops), then hands them to the sealed ``places`` index.
Nothing is fetched from Google here — we only read a file you already have.

Formats handled (they've changed over the years — we sniff and adapt):
  1. Semantic Location History — ``…/Semantic Location History/2024/2024_MARCH.json``
     with ``timelineObjects[].placeVisit`` (named place + address + lat/lng + times).
     The richest source: real place names.
  2. On-device Timeline export — a single JSON with ``semanticSegments[].visit``
     (newer phone export) or a top-level ``timelineObjects`` list.
  3. Raw ``Records.json`` — location pings only (lat/lng/time, no names). We keep
     these as coordinate-only visits so the map/day still has data, labelled by
     coordinates (no invented place names).

Only *visits* (stops) become records — we skip raw travel paths, since "places you
went" is the useful signal. E7 coordinates (integer × 1e7) are converted to floats.

CLI:
    python3 -m cognitive_twin.importers.google_timeline <file-or-folder> [--dry-run]

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator

from ..places import Visit, import_visits, is_enabled


_SOURCE = "google-timeline"


# ── coordinate helpers ─────────────────────────────────────────────────────────
def _e7(v: Any) -> float | None:
    """Google stores lat/lng as integer degrees × 1e7 in older exports."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    # A plausible E7 value is huge (e.g. 436532000); a plain degree is small.
    return f / 1e7 if abs(f) > 1000 else f


def _latlng(obj: dict[str, Any]) -> tuple[float | None, float | None]:
    # Various shapes: latE7/lngE7, latitudeE7, latitude, "latLng": "43.6,-79.3"
    for lat_k, lon_k in (("latE7", "lngE7"), ("latitudeE7", "longitudeE7"),
                         ("latitude", "longitude")):
        if lat_k in obj and lon_k in obj:
            return _e7(obj[lat_k]), _e7(obj[lon_k])
    if "latLng" in obj and isinstance(obj["latLng"], str):
        try:
            a, b = obj["latLng"].replace("°", "").split(",")
            return float(a), float(b)
        except ValueError:
            pass
    return None, None


def _iso(ts: Any) -> str | None:
    """Normalise a timestamp (ISO string, or {timestamp/ timestampMs}) to ISO."""
    if not ts:
        return None
    if isinstance(ts, str):
        return ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
    if isinstance(ts, dict):
        return _iso(ts.get("timestamp") or ts.get("timestampMs"))
    # epoch millis
    try:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


# ── visit extractors for each format ───────────────────────────────────────────
def _from_place_visit(pv: dict[str, Any]) -> Visit | None:
    """Semantic Location History placeVisit → Visit."""
    loc = pv.get("location", {}) or {}
    dur = pv.get("duration", {}) or {}
    lat, lon = _latlng(loc)
    start = _iso(dur.get("startTimestamp") or dur.get("startTimestampMs"))
    end = _iso(dur.get("endTimestamp") or dur.get("endTimestampMs"))
    if not start:
        return None
    name = (loc.get("name") or loc.get("address") or "").strip()
    if not name and lat is not None:
        name = f"{lat:.4f},{lon:.4f}"
    if not name:
        return None
    conf = pv.get("placeVisitImportance")
    return Visit(place=name, start=start, end=end, lat=lat, lon=lon,
                 source=_SOURCE,
                 category=(loc.get("semanticType") or "").replace("TYPE_", "").lower() or None,
                 meta={k: v for k, v in {"placeId": loc.get("placeId"),
                                         "address": loc.get("address"),
                                         "importance": conf}.items() if v})


def _from_new_visit(seg: dict[str, Any]) -> Visit | None:
    """On-device export semanticSegments[].visit → Visit."""
    visit = seg.get("visit") or {}
    tpl = (visit.get("topCandidate") or {})
    place = (tpl.get("placeLocation", {}).get("name")
             or tpl.get("semanticType")
             or "").strip()
    latlng = tpl.get("placeLocation", {}).get("latLng") or seg.get("startLatLng")
    lat = lon = None
    if isinstance(latlng, str):
        try:
            a, b = latlng.replace("°", "").split(",")
            lat, lon = float(a), float(b)
        except ValueError:
            pass
    start = _iso(seg.get("startTime"))
    end = _iso(seg.get("endTime"))
    if not start:
        return None
    if not place and lat is not None:
        place = f"{lat:.4f},{lon:.4f}"
    if not place:
        return None
    return Visit(place=place, start=start, end=end, lat=lat, lon=lon, source=_SOURCE)


def _visits_from_obj(data: Any) -> Iterator[Visit]:
    """Yield visits from any recognised top-level shape."""
    if isinstance(data, dict):
        # Format 1: Semantic Location History (timelineObjects)
        for obj in data.get("timelineObjects", []) or []:
            if "placeVisit" in obj:
                v = _from_place_visit(obj["placeVisit"])
                if v:
                    yield v
        # Format 2: on-device export (semanticSegments)
        for seg in data.get("semanticSegments", []) or []:
            if "visit" in seg:
                v = _from_new_visit(seg)
                if v:
                    yield v
        # Format 3: raw Records.json (locations) — coordinate-only visits
        for rec in data.get("locations", []) or []:
            lat, lon = _latlng(rec)
            start = _iso(rec.get("timestamp") or rec.get("timestampMs"))
            if lat is not None and start:
                yield Visit(place=f"{lat:.4f},{lon:.4f}", start=start,
                            lat=lat, lon=lon, source=_SOURCE,
                            meta={"raw_ping": True})
    elif isinstance(data, list):
        # Some exports are a bare list of timelineObjects
        for obj in data:
            if isinstance(obj, dict) and "placeVisit" in obj:
                v = _from_place_visit(obj["placeVisit"])
                if v:
                    yield v


# ── file / folder walking ──────────────────────────────────────────────────────
def _json_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    if target.is_dir():
        # Common Takeout locations, plus any *.json under the folder.
        return sorted(target.rglob("*.json"))
    return []


def parse(target: str | Path) -> list[Visit]:
    """Parse all recognised place-visits from a file or folder (no side effects)."""
    target = Path(target).expanduser()
    visits: list[Visit] = []
    for f in _json_files(target):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        visits.extend(_visits_from_obj(data))
    # stable order by start time
    visits.sort(key=lambda v: v.start)
    return visits


def import_from(target: str | Path) -> dict[str, Any]:
    """Parse + push into the sealed places index (honours the opt-in gate)."""
    if not is_enabled():
        return {"imported": 0, "parsed": 0,
                "note": "place tracking is off — run `places enable` first."}
    visits = parse(target)
    n = import_visits(visits)
    return {"imported": n, "parsed": len(visits)}


# ── CLI ─────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    if not argv:
        print("usage: python3 -m cognitive_twin.importers.google_timeline "
              "<file-or-folder> [--dry-run]")
        return 2
    target = argv[0]
    dry = "--dry-run" in argv
    if dry:
        visits = parse(target)
        print(f"Parsed {len(visits)} place-visit(s) from {target} (dry run).")
        for v in visits[:15]:
            print(f"  {v.start[:16]}  {v.place}")
        if len(visits) > 15:
            print(f"  … and {len(visits) - 15} more")
        return 0
    r = import_from(target)
    if r.get("note"):
        print(r["note"]); return 1
    print(f"✓ Imported {r['imported']} new visit(s) "
          f"(parsed {r['parsed']}) into the sealed places index.")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
