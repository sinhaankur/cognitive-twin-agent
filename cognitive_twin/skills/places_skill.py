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
