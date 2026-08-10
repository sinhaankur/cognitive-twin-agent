"""
apple_locations — read macOS's own on-device location store into the places index.

macOS keeps location data locally in two places worth reading:
  1. **Significant Locations** — the places you frequent, in a set of protected
     ``.plist`` caches under
     ``/private/var/mobile/Library/Caches/com.apple.routined/`` (iOS) and, on the
     Mac, under ``~/Library/Caches`` / the Location Services bundle. These are
     SIP/Full-Disk-Access protected.
  2. **knowledgeC.db** — the on-device usage database, which can hold
     ``/location/visit`` events (arrive/leave with coordinates). It lives at
     ``~/Library/Application Support/Knowledge/knowledgeC.db`` and needs **Full
     Disk Access** for the terminal/Python running this.

Apple gives no API for either — this reads the local files directly. It is
best-effort and honest: if the files aren't reachable (no Full Disk Access, or a
macOS version that changed the schema), it says exactly that instead of pretending.
Nothing leaves the Mac.

Grant access: System Settings → Privacy & Security → **Full Disk Access** → add
your terminal (or the Python binary). Then:

    python3 -m cognitive_twin.importers.apple_locations import
    python3 -m cognitive_twin.importers.apple_locations check    # what's reachable?

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..places import Visit, import_visits, is_enabled

_SOURCE = "apple-significant"

# knowledgeC stores timestamps as seconds since the Cocoa epoch (2001-01-01 UTC).
_COCOA_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)


def _knowledge_db() -> Path:
    return Path.home() / "Library" / "Application Support" / "Knowledge" / "knowledgeC.db"


def _cocoa_to_iso(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    try:
        return (_COCOA_EPOCH + timedelta(seconds=float(seconds))).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def check() -> dict[str, Any]:
    """Report what's reachable, so the user knows if Full Disk Access is needed."""
    db = _knowledge_db()
    out: dict[str, Any] = {"knowledgeC_path": str(db), "knowledgeC_readable": False,
                           "visit_events": None, "note": ""}
    if not db.is_file():
        out["note"] = "knowledgeC.db not found (unusual — may be a very new macOS)."
        return out
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        try:
            cur = con.execute(
                "SELECT COUNT(*) FROM ZOBJECT WHERE ZSTREAMNAME = '/location/visit'")
            out["knowledgeC_readable"] = True
            out["visit_events"] = cur.fetchone()[0]
        finally:
            con.close()
    except sqlite3.OperationalError as e:
        out["note"] = (f"can't read knowledgeC.db ({e}). Grant Full Disk Access to "
                       f"your terminal in System Settings → Privacy & Security.")
    return out


def _read_knowledge_visits(limit: int = 5000) -> list[Visit]:
    """Pull /location/visit events from knowledgeC.db (best-effort)."""
    db = _knowledge_db()
    if not db.is_file():
        return []
    visits: list[Visit] = []
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    except sqlite3.OperationalError:
        return []
    try:
        # Schema varies across macOS versions; we read the common columns and
        # guard each row. ZVALUESTRING often carries the place label; the
        # structured metadata table holds lat/lon on some versions.
        try:
            rows = con.execute(
                "SELECT ZSTARTDATE, ZENDDATE, ZVALUESTRING "
                "FROM ZOBJECT WHERE ZSTREAMNAME='/location/visit' "
                "ORDER BY ZSTARTDATE DESC LIMIT ?", (limit,)).fetchall()
        except sqlite3.OperationalError:
            return []
        for start_s, end_s, label in rows:
            start = _cocoa_to_iso(start_s)
            if not start:
                continue
            place = (label or "").strip() or "Visited place"
            visits.append(Visit(place=place, start=start, end=_cocoa_to_iso(end_s),
                                source=_SOURCE, meta={"from": "knowledgeC"}))
    finally:
        con.close()
    return visits


def parse() -> list[Visit]:
    """All Apple-side visits we can read on this Mac (best-effort)."""
    visits = _read_knowledge_visits()
    visits.sort(key=lambda v: v.start)
    return visits


def import_now() -> dict[str, Any]:
    if not is_enabled():
        return {"imported": 0, "note": "place tracking is off — run `places enable`."}
    chk = check()
    if not chk["knowledgeC_readable"]:
        return {"imported": 0, "note": chk["note"] or
                "Apple location store not readable (Full Disk Access likely needed)."}
    visits = parse()
    n = import_visits(visits)
    return {"imported": n, "parsed": len(visits)}


def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "check"
    if cmd == "check":
        c = check()
        print(f"knowledgeC.db: {c['knowledgeC_path']}")
        if c["knowledgeC_readable"]:
            print(f"  ✓ readable — {c['visit_events']} location/visit event(s) present.")
        else:
            print(f"  ✗ {c['note']}")
        return 0
    if cmd == "import":
        r = import_now()
        if r.get("note"):
            print(r["note"]); return 1
        print(f"✓ Imported {r['imported']} Apple location visit(s) "
              f"(parsed {r['parsed']}) into the sealed index.")
        return 0
    print("usage: python3 -m cognitive_twin.importers.apple_locations [check|import]")
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
