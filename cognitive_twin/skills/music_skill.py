"""
music_skill — Vera's music awareness as agent skills.

So the twin can answer "what am I listening to?" / "what do I listen to most?"
from the on-device, sealed music log (``music.py`` — macOS Now Playing). Read-only
reporting; turning tracking on/off is an explicit, separate action. Nothing leaves
the Mac.

Importing this module registers the skills on the default registry.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

from .base import default_registry as R


@R.add(
    "now_playing",
    "What you're listening to right now, read from macOS Now Playing (Apple Music "
    "/ Spotify). Read-only, on-device. Says so if nothing's playing.",
    {"type": "object", "properties": {}},
)
def now_playing() -> str:
    from .. import music
    p = music.now()
    if not p:
        return "Nothing's playing right now."
    where = f" ({p.app})" if p.app else ""
    return f"Now playing: {p.title}" + (f" — {p.artist}" if p.artist else "") + where


@R.add(
    "music_taste",
    "What you listen to most — your top artists and tracks across all logged "
    "history (or the last N days), from the on-device music log. Read-only.",
    {"type": "object", "properties": {
        "days": {"type": "integer",
                 "description": "optional: only the last N days (omit for all time)"},
    }},
)
def music_taste(days: int = 0) -> str:
    from .. import music
    return music.summarize_taste(since_days=days if days and days > 0 else None)


@R.add(
    "music_status",
    "Whether music tracking is on, and how many plays are stored (all sealed on "
    "this Mac). Read-only.",
    {"type": "object", "properties": {}},
)
def music_status() -> str:
    from .. import music
    return music.status()


@R.add(
    "enable_music_tracking",
    "Turn on Vera's on-device music tracking (opt-in). She then reads macOS Now "
    "Playing and keeps a sealed log of the tracks you play. Pass on=false to stop.",
    {"type": "object", "properties": {
        "on": {"type": "boolean", "description": "true to enable, false to disable (default true)"},
    }},
)
def enable_music_tracking(on: bool = True) -> str:
    from .. import music
    if on:
        music.enable()
        return ("Music tracking is on (opt-in, sealed on this Mac). I'll read Now "
                "Playing and learn what you listen to.")
    music.disable()
    return "Music tracking is off."
