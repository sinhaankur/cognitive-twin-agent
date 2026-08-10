"""
core_location — this Mac's *current* location, on demand, via CoreLocation.

The lightest source: where this Mac is right now. Useful for "log where I am" and
as a live signal when the phone-based sources aren't set up. It uses Apple's
**CoreLocation** through PyObjC (``pyobjc-framework-CoreLocation``); if that isn't
installed, it says so honestly rather than guessing a location.

macOS will prompt for Location Services permission the first time (System Settings
→ Privacy & Security → Location Services). Nothing leaves the Mac.

    pip install pyobjc-framework-CoreLocation      # one-time, if you want this source
    python3 -m cognitive_twin.importers.core_location where    # print current location
    python3 -m cognitive_twin.importers.core_location log       # add it to the places index

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from ..places import Visit, record, is_enabled

_SOURCE = "core-location"


class _Unavailable(RuntimeError):
    pass


def _current_coords(timeout_s: float = 8.0) -> tuple[float, float]:
    """Return (lat, lon) from CoreLocation, or raise _Unavailable with guidance."""
    try:
        from CoreLocation import CLLocationManager  # type: ignore
        from Foundation import NSRunLoop, NSDate      # type: ignore
    except Exception:
        raise _Unavailable(
            "CoreLocation isn't available. Install it once with:\n"
            "  pip install pyobjc-framework-CoreLocation")

    mgr = CLLocationManager.alloc().init()
    if hasattr(mgr, "requestWhenInUseAuthorization"):
        mgr.requestWhenInUseAuthorization()
    mgr.startUpdatingLocation()

    deadline = time.time() + timeout_s
    loc = None
    while time.time() < deadline:
        loc = mgr.location()
        if loc is not None:
            break
        # pump the run loop so CoreLocation can deliver a fix
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.2))
    mgr.stopUpdatingLocation()

    if loc is None:
        raise _Unavailable(
            "No location fix (permission denied, or Location Services off). "
            "Enable it in System Settings → Privacy & Security → Location Services.")
    c = loc.coordinate()
    return float(c.latitude), float(c.longitude)


def where() -> dict[str, Any]:
    """Current coordinates (no side effects). Returns {'lat','lon'} or {'note'}."""
    try:
        lat, lon = _current_coords()
    except _Unavailable as e:
        return {"note": str(e)}
    return {"lat": lat, "lon": lon, "time": datetime.now(timezone.utc).isoformat()}


def log(place: str | None = None) -> dict[str, Any]:
    """Record the current location as a point-visit in the sealed index."""
    if not is_enabled():
        return {"logged": False, "note": "place tracking is off — run `places enable`."}
    w = where()
    if w.get("note"):
        return {"logged": False, "note": w["note"]}
    name = place or f"{w['lat']:.4f},{w['lon']:.4f}"
    ok = record(Visit(place=name, start=w["time"], lat=w["lat"], lon=w["lon"],
                      source=_SOURCE))
    return {"logged": bool(ok), "place": name, "lat": w["lat"], "lon": w["lon"]}


def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "where"
    if cmd == "where":
        w = where()
        if w.get("note"):
            print(w["note"]); return 1
        print(f"You're at {w['lat']:.5f}, {w['lon']:.5f} (as of now).")
        return 0
    if cmd == "log":
        name = argv[1] if len(argv) > 1 else None
        r = log(name)
        if not r["logged"]:
            print(r["note"]); return 1
        print(f"✓ Logged: {r['place']} ({r['lat']:.4f}, {r['lon']:.4f}).")
        return 0
    print("usage: python3 -m cognitive_twin.importers.core_location [where|log]")
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
