"""
watchtower_skill — Vera's observability link, as agent skills.

Lets the twin answer "is my stack healthy?" and report its own operational
health to a *local* WatchTower (see ``watchtower.py``). Off by default,
local-only, read-first — nothing is emitted until the user opts in, and only
operational metadata ever leaves (never conversation, persona, or memory).

Importing this module registers the skills on the default registry.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

from .base import default_registry as R


def _cfg():
    # Lazy import so the skill module stays cheap to import.
    try:
        from ..cli import _load_config
        return _load_config()
    except Exception:
        return {}


@R.add(
    "watchtower_status",
    "Report the WatchTower link: whether Vera's observability is on, and whether "
    "a local WatchTower instance is up and reachable. Read-only. If the link is "
    "off (the default) it says how to turn it on.",
    {"type": "object", "properties": {}},
)
def watchtower_status() -> str:
    from .. import watchtower
    return watchtower.summarize_health(_cfg())


@R.add(
    "watchtower_note",
    "Record a one-line operational note/marker to WatchTower (e.g. 'deployed "
    "vera v2', 'switched to unhosted 14B'). Only works if the WatchTower link is "
    "on; otherwise it says so. Operational metadata only — no personal content.",
    {"type": "object", "properties": {
        "text": {"type": "string", "description": "short operational note to mark on the timeline"},
    }, "required": ["text"]},
)
def watchtower_note(text: str) -> str:
    from .. import watchtower
    cfg = _cfg()
    if not watchtower.is_enabled(cfg):
        return ("WatchTower link is off — nothing recorded. Turn it on with "
                "`CTWIN_WATCHTOWER=1` (or watchtower.enabled in the agent config).")
    ok = watchtower.emit("note", cfg, text=text[:280])
    return "Noted on WatchTower." if ok else (
        "WatchTower link is on but the instance didn't answer — is it running?")
