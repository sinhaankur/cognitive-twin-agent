"""
ios_shortcut — live 'where am I now' from an Apple Shortcut, the Apple-Maps way.

Apple gives no location-history API (privacy by design), so the clean, fully-yours
path for Apple-side location is a **Shortcut on your iPhone** that, on arrival at a
place (or on a tap / an automation), appends your current place to a small JSON
file in iCloud Drive. Vera watches that file and folds each entry into the sealed
places index. Your phone is the sensor; this Mac is the brain; nothing goes to a
third party.

The Shortcut writes newline-delimited JSON (one object per arrival), e.g.:
    {"place":"Equinox Bay St","lat":43.647,"lon":-79.381,"time":"2026-08-10T18:03:00Z","category":"gym"}
Fields: ``place`` (required), ``lat``/``lon`` (optional), ``time`` (ISO; defaults
to now if absent), ``category``/``end`` optional. We track a byte offset so each
poll only ingests new lines (idempotent).

The watch file defaults to
``~/Library/Mobile Documents/com~apple~CloudDocs/Vera/places.ndjson`` (your iCloud
Drive → a "Vera" folder), override with ``CTWIN_IOS_PLACES_FILE``.

How to build the Shortcut (once) — see the printed guide:
    python3 -m cognitive_twin.importers.ios_shortcut guide

CLI:
    python3 -m cognitive_twin.importers.ios_shortcut poll     # ingest new lines now
    python3 -m cognitive_twin.importers.ios_shortcut path      # show the watch file
    python3 -m cognitive_twin.importers.ios_shortcut guide     # Shortcut build steps

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import security
from ..places import Visit, import_visits, is_enabled

_SOURCE = "ios-shortcut"
_OFFSET_STATE = "ios_shortcut_offset.json"   # sealed: byte offset already ingested


def watch_file() -> Path:
    default = (Path.home() / "Library" / "Mobile Documents"
               / "com~apple~CloudDocs" / "Vera" / "places.ndjson")
    return Path(os.environ.get("CTWIN_IOS_PLACES_FILE", str(default))).expanduser()


def _offset() -> int:
    st = security.read_state(security.path(_OFFSET_STATE), default={}) or {}
    return int(st.get(str(watch_file()), 0))


def _save_offset(n: int) -> None:
    st = security.read_state(security.path(_OFFSET_STATE), default={}) or {}
    st[str(watch_file())] = n
    security.write_state(security.path(_OFFSET_STATE), st)


def _to_visit(obj: dict[str, Any]) -> Visit | None:
    place = (obj.get("place") or obj.get("name") or "").strip()
    if not place:
        # Fall back to coords if the Shortcut only sent a location.
        lat, lon = obj.get("lat"), obj.get("lon")
        if lat is None or lon is None:
            return None
        place = f"{float(lat):.4f},{float(lon):.4f}"
    time = obj.get("time") or obj.get("start") or datetime.now(timezone.utc).isoformat()
    if isinstance(time, str) and time.endswith("Z"):
        time = time.replace("Z", "+00:00")
    lat = obj.get("lat")
    lon = obj.get("lon")
    return Visit(
        place=place,
        start=time,
        end=obj.get("end"),
        lat=float(lat) if lat is not None else None,
        lon=float(lon) if lon is not None else None,
        source=_SOURCE,
        category=obj.get("category"),
    )


def poll() -> dict[str, Any]:
    """Ingest any new lines appended since last poll (idempotent via byte offset)."""
    if not is_enabled():
        return {"imported": 0, "note": "place tracking is off — run `places enable`."}
    f = watch_file()
    if not f.is_file():
        return {"imported": 0, "note": f"no watch file yet at {f} — set up the Shortcut "
                                       f"(`ios_shortcut guide`)."}
    start = _offset()
    size = f.stat().st_size
    if size < start:            # file was truncated/rotated — re-read from 0
        start = 0
    visits: list[Visit] = []
    with f.open("r", encoding="utf-8") as fh:
        fh.seek(start)
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            v = _to_visit(obj)
            if v:
                visits.append(v)
        new_offset = fh.tell()
    n = import_visits(visits)
    _save_offset(new_offset)
    return {"imported": n, "parsed": len(visits), "file": str(f)}


_GUIDE = """\
Build the iPhone Shortcut once (Apple-Maps location, all yours):

  1. Files app → iCloud Drive → New Folder "Vera".
  2. Shortcuts app → New Shortcut → add these actions:
       • Get Current Location
       • Get [Name] from  (Location)          → the place name
       • Text:  {"place":"[Name]","lat":[Latitude],"lon":[Longitude],
                 "time":"[Current Date, ISO 8601]"}
       • Append to Text File
             File: iCloud Drive / Vera / places.ndjson   (create if missing)
             Add a newline after: ON
  3. (Optional) Automation → "Arrive" at places you care about → Run this Shortcut,
     so it logs automatically when you get somewhere.
  4. On the Mac:  python3 -m cognitive_twin.importers.ios_shortcut poll
     (or let Vera poll it on a timer).

Each run only reads new lines, so it's safe to poll often.
"""


def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "poll"
    if cmd == "path":
        print(watch_file()); return 0
    if cmd == "guide":
        print(_GUIDE); return 0
    if cmd == "poll":
        r = poll()
        if r.get("note"):
            print(r["note"]); return 1
        print(f"✓ Ingested {r['imported']} new place(s) from the iOS shortcut file.")
        return 0
    print("usage: python3 -m cognitive_twin.importers.ios_shortcut [poll|path|guide]")
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
