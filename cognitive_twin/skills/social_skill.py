"""
social_skill — Vera's Facebook/Instagram awareness as agent skills.

Reports from the sealed on-device social index (``social.py``), fed by your Meta
"Download Your Information" export. Read-only reporting; importing is an explicit
action with a path. Nothing leaves the Mac; sentiment is on-device and labelled as
inference.

Importing this module registers the skills on the default registry.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

from .base import default_registry as R


@R.add(
    "social_summary",
    "Summarise your Facebook/Instagram activity from the on-device index: how much "
    "you post, the tone of what you write (on-device sentiment, inference), who you "
    "engage with, and when you're active. Read-only.",
    {"type": "object", "properties": {
        "days": {"type": "integer", "description": "window in days (default 90)"},
    }},
)
def social_summary(days: int = 90) -> str:
    from .. import social
    return social.summary(days)


@R.add(
    "social_status",
    "Whether social tracking is on and how many items are indexed (sealed on this "
    "Mac). Read-only.",
    {"type": "object", "properties": {}},
)
def social_status() -> str:
    from .. import social
    return social.status()


@R.add(
    "import_meta_export",
    "Import a Meta 'Download Your Information' export (Facebook + Instagram) from a "
    "folder into the sealed social index, scoring sentiment on-device. Give the path "
    "to the unzipped export folder.",
    {"type": "object", "properties": {
        "path": {"type": "string", "description": "path to the unzipped Meta export folder"},
    }, "required": ["path"]},
)
def import_meta_export(path: str) -> str:
    from .. import social
    from ..importers import meta_export as M
    if not social.is_enabled():
        return ("Social tracking is off. Enable it first: "
                "python3 -m cognitive_twin.social enable")
    r = M.import_from(path)
    return r.get("note") or (
        f"Imported {r['imported']} activities (parsed {r['parsed']}) from your Meta "
        f"export into the sealed index.")


@R.add(
    "enable_social_tracking",
    "Turn on Vera's on-device social tracking (opt-in). Pass on=false to turn off.",
    {"type": "object", "properties": {
        "on": {"type": "boolean", "description": "true to enable, false to disable"},
    }},
)
def enable_social_tracking(on: bool = True) -> str:
    from .. import social
    if on:
        social.enable()
        return ("Social tracking is on (opt-in, sealed on this Mac). Import your "
                "Meta export next to populate it.")
    social.disable()
    return "Social tracking is off."
