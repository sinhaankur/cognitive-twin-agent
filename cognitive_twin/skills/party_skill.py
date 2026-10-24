"""
party_skill — Vera's laser "party mode" as agent skills.

So you can say "lights on" / "start the party" / "lights off" and Vera runs the
BTK10 sound-reactive laser: route audio to it (beams react to the music), then
put your sound back when you're done. Opt-in, named safe actions only, all local
(no network) — see party.py. Importing this module registers the skills.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

from .base import default_registry as R


@R.add(
    "lights_on",
    "Start the laser light show: connect the BTK10 sound-reactive laser, send the "
    "Mac's audio to it so the beams pulse with the music, and start music. "
    "Remembers your current speakers so 'lights off' restores them. Opt-in.",
    {"type": "object", "properties": {
        "music": {"type": "boolean",
                  "description": "also start Apple Music so there's a beat (default true)"},
    }},
)
def lights_on(music: bool = True) -> str:
    from .. import party
    return party.lights_on(music=music)


@R.add(
    "lights_off",
    "End the laser show: put your sound back on your speakers and pause the music. "
    "Always safe to call.",
    {"type": "object", "properties": {}},
)
def lights_off() -> str:
    from .. import party
    return party.lights_off()


@R.add(
    "party_status",
    "Where the laser show stands: whether party mode is on (opt-in), whether the "
    "BTK10 laser is connected, and which audio output is active. Read-only.",
    {"type": "object", "properties": {}},
)
def party_status() -> str:
    from .. import party
    return party.status()


@R.add(
    "enable_party_mode",
    "Turn Vera's laser party mode on or off (opt-in; off by default). Pass on=false "
    "to disable. When off, the lights actions stay inert.",
    {"type": "object", "properties": {
        "on": {"type": "boolean", "description": "true to enable, false to disable (default true)"},
    }},
)
def enable_party_mode(on: bool = True) -> str:
    from .. import party
    party.enable(on)
    return ("Party mode is on — say 'lights on' to start the show."
            if on else "Party mode is off.")
