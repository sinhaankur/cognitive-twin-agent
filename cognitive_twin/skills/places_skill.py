"""
places_skill — Vera's location awareness as agent skills.

So the twin can answer "where did I go today?" / "where have I been this week?"
from the on-device, sealed places index (``places.py``). Read-only reporting;
turning tracking on/off is an explicit, separate action. Nothing leaves the Mac.

Importing this module registers the skills on the default registry.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

from .base import default_registry as R


@R.add(
    "places_today",
    "Where you went today, from Vera's on-device location index. Read-only. If "
    "tracking is off or no source is connected, it says so.",
    {"type": "object", "properties": {}},
)
def places_today() -> str:
    from .. import places
    return places.summarize_day(places.today(), label="today")


@R.add(
    "places_week",
    "Where you've been over the last 7 days, grouped by day, from the on-device "
    "location index. Read-only.",
    {"type": "object", "properties": {}},
)
def places_week() -> str:
    from .. import places
    if not places.is_enabled():
        return places.summarize_day([], label="this week")
    wk = places.week()
    if not wk:
        return "No places logged in the last 7 days."
    return "\n\n".join(places.summarize_day(vs, label=day) for day, vs in wk.items())


@R.add(
    "places_status",
    "Whether location tracking is on, and how many visits are stored (all sealed "
    "on this Mac). Read-only.",
    {"type": "object", "properties": {}},
)
def places_status() -> str:
    from .. import places
    return places.status()


@R.add(
    "enable_place_tracking",
    "Turn on Vera's on-device location tracking (opt-in). After enabling, connect "
    "a source (Google Timeline export, Apple locations, or the iOS shortcut). "
    "Pass on=false to turn it off.",
    {"type": "object", "properties": {
        "on": {"type": "boolean", "description": "true to enable, false to disable (default true)"},
    }},
)
def enable_place_tracking(on: bool = True) -> str:
    from .. import places
    if on:
        places.enable()
        return ("Location tracking is on (opt-in, sealed on this Mac). Connect a "
                "source next to start logging where you go.")
    places.disable()
    return "Location tracking is off."


@R.add(
    "import_places",
    "Pull location data into Vera's sealed index from a source: a Google Timeline/"
    "Takeout export (give the file/folder path), the iOS Shortcut file, macOS Apple "
    "locations, or this Mac's current location. Read-only on your data.",
    {"type": "object", "properties": {
        "source": {"type": "string",
                    "description": "one of: google, ios, apple, here"},
        "path": {"type": "string",
                 "description": "file/folder path (required for source=google)"},
    }, "required": ["source"]},
)
def import_places(source: str, path: str = "") -> str:
    src = (source or "").lower().strip()
    if src in ("google", "timeline", "takeout"):
        if not path:
            return "Give the path to your Google Takeout/Timeline file or folder."
        from ..importers import google_timeline as G
        r = G.import_from(path)
        return r.get("note") or f"Imported {r['imported']} visit(s) from Google Timeline."
    if src in ("ios", "shortcut"):
        from ..importers import ios_shortcut as S
        r = S.poll()
        return r.get("note") or f"Ingested {r['imported']} place(s) from the iOS shortcut."
    if src in ("apple", "significant", "macos"):
        from ..importers import apple_locations as A
        r = A.import_now()
        return r.get("note") or f"Imported {r['imported']} Apple location visit(s)."
    if src in ("here", "now", "core", "current"):
        from ..importers import core_location as C
        r = C.log()
        return (r.get("note") if not r.get("logged")
                else f"Logged where you are now: {r['place']}.")
    return "Unknown source. Use: google (with path), ios, apple, or here."
