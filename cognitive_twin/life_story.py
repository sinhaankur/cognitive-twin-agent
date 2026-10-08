"""
Life Story — the lived past that makes the twin *them*, not a warm assistant.

A persona gives the twin a character (warm, patient, honest). But a twin of
someone you love feels like THEM only when it carries their actual life: the
people they loved, where they grew up, the things they always said, the small
stories that were theirs. This module holds that — a structured, on-device,
sealed memory of a real person's life — and compiles it into the system prompt
so the twin speaks *from a real past*, in their own turns of phrase.

Shape (every field optional — you fill what you have, over time):
  - people    : who mattered, and who they were ("Ankur — my son", "Randhir — my husband")
  - places    : where life happened ("Munger, where I grew up", "our home in Ranchi")
  - sayings   : the phrases they ACTUALLY used — the "it's really them" signal
  - stories   : small true memories, in their own words
  - loves     : foods, songs, rituals, small joys that were specifically theirs
  - dates     : anchors that shaped them (a wedding, a move, a loss)

Privacy, absolute: this is the single most personal file in the system — a real
person's life. It is sealed at rest via the security kernel (same as persona),
stored only on this machine, never synced, never a network surface. See
[[project_vera_security_kernel]] and PRIVACY.md.

Honesty rule (carried from the soul layer): the twin speaks FROM this life, but
never INVENTS a memory that isn't here. If asked about something not recorded,
she says she doesn't remember rather than fabricating — a twin that makes up the
past isn't them. The prompt block makes that explicit to the model.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field, asdict
from pathlib import Path


def _dir() -> Path:
    root = Path(os.environ.get("CTWIN_PERSONA_DIR",
                               os.environ.get("CTWIN_MEMORY_DIR", Path.home() / ".cognitive-twin")))
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, stat.S_IRWXU)
    except OSError:
        pass
    return root


def _file() -> Path:
    return _dir() / "life_story.json"


@dataclass
class Person:
    """Someone who mattered to them."""
    name: str = ""
    relation: str = ""   # "son", "husband", "sister", "dearest friend"
    note: str = ""       # a line of who they were to them


@dataclass
class Story:
    """A small true memory, ideally in their own words."""
    title: str = ""
    text: str = ""
    when: str = ""       # a free-text anchor ("when Ankur was small", "1985")


@dataclass
class LifeStory:
    """A real person's life, held on-device. Every field optional."""
    people: list[Person] = field(default_factory=list)
    places: list[str] = field(default_factory=list)
    sayings: list[str] = field(default_factory=list)      # their actual phrases
    stories: list[Story] = field(default_factory=list)
    loves: list[str] = field(default_factory=list)        # foods, songs, rituals
    dates: list[str] = field(default_factory=list)        # "married 1974", "moved to Ranchi 1990"

    def is_empty(self) -> bool:
        return not any([self.people, self.places, self.sayings,
                        self.stories, self.loves, self.dates])

    def to_prompt(self, include_sayings: bool = True) -> str:
        """Compile the lived past into a system-prompt block, written so the model
        speaks FROM this life without inventing beyond it.

        include_sayings=False omits the phrases list — used when the moment's
        sayings-hint will carry them, so a tiny model never sees them twice."""
        if self.is_empty():
            return ""
        lines: list[str] = [
            "# YOUR LIFE (the real past you carry)",
            "Your actual life — speak from it naturally. Reference these people, "
            "places and memories when they fit, in your own words. Never invent "
            "beyond what's here; if asked about something not here, gently say you "
            "don't quite remember.",
        ]
        if self.people:
            who = "; ".join(
                f"{p.name}" + (f" ({p.relation})" if p.relation else "")
                + (f" — {p.note}" if p.note else "")
                for p in self.people if p.name
            )
            if who:
                lines.append("The people who matter to you: " + who + ".")
        if self.places:
            lines.append("Places that are yours: " + "; ".join(self.places) + ".")
        if self.dates:
            lines.append("Life anchors: " + "; ".join(self.dates) + ".")
        if self.loves:
            lines.append("Small joys that are specifically yours: " + "; ".join(self.loves) + ".")
        if self.sayings and include_sayings:
            # The strongest "it's really them" cue — surfaced explicitly. Omitted
            # when the moment's sayings-hint will carry these instead (no double).
            quoted = "; ".join(f"“{s}”" for s in self.sayings)
            lines.append(
                "Things you actually say — your own turns of phrase, use them "
                "naturally when they fit (never forced): " + quoted + "."
            )
        if self.stories:
            lines.append("Memories that are yours:")
            for s in self.stories:
                if not s.text:
                    continue
                head = (s.title or "A memory") + (f" ({s.when})" if s.when else "")
                lines.append(f"  - {head}: {s.text}")
        return "\n".join(lines)

    def sayings_for(self, _prompt: str = "") -> list[str]:
        """Her actual phrases — exposed so a reply can lean on a real one at the
        right moment (the voice_profile layer can weave these in)."""
        return list(self.sayings)


# The moments where leaning on a real phrase actually lands. On a neutral,
# factual turn ("what's 2+2") a saying would feel forced, so the hint stays
# silent and her phrases live in the life block instead (no duplication).
_HINT_MOMENTS = {"heavy", "tender", "bright", "glad"}


def hint_fires(label: str) -> bool:
    """True when the sayings-hint should fire this turn — only on a real
    emotional moment, and only if she has sayings. Used by the loop to decide
    whether to omit sayings from the life block (so they're never listed twice)."""
    return label in _HINT_MOMENTS and bool(load().sayings)


def moment_hint(label: str = "") -> str:
    """A tiny, moment-aware nudge to lean on ONE of her real sayings when it
    genuinely fits the emotion — the thing that makes a reply land as 'that's
    exactly how she'd say it.' Fires ONLY on an emotional moment (so it never
    pads a neutral turn); returns "" otherwise. Never forces a phrase.

    `label` is the live felt read (feel.Felt.label): heavy/tender/bright/glad.
    """
    ls = load()
    if not ls.sayings or label not in _HINT_MOMENTS:
        return ""
    quoted = "; ".join(f"“{s}”" for s in ls.sayings[:8])
    mood = (" A tender moment — if one of her gentler phrases fits, let it come through."
            if label in ("heavy", "tender")
            else " A warm moment — a familiar, glad phrase of hers may fit.")
    return (
        "HER real phrases (use at most one, only if it lands — never force it, "
        "never invent one): " + quoted + "." + mood
    )


# ---- load / save (local, owner-only, SEALED) ---------------------------------
def load() -> LifeStory:
    from . import security
    data = security.read_state(_file(), default=None)
    if not data:
        return LifeStory()
    try:
        people = [Person(**{k: v for k, v in p.items() if k in Person().__dataclass_fields__})  # type: ignore[attr-defined]
                  for p in data.get("people", []) if isinstance(p, dict)]
        stories = [Story(**{k: v for k, v in s.items() if k in Story().__dataclass_fields__})  # type: ignore[attr-defined]
                   for s in data.get("stories", []) if isinstance(s, dict)]
        return LifeStory(
            people=people,
            places=list(data.get("places", [])),
            sayings=list(data.get("sayings", [])),
            stories=stories,
            loves=list(data.get("loves", [])),
            dates=list(data.get("dates", [])),
        )
    except (TypeError, ValueError):
        return LifeStory()


def save(ls: LifeStory) -> None:
    from . import security
    try:
        security.write_state(_file(), asdict(ls))
    except Exception:
        pass


def to_prompt(include_sayings: bool = True) -> str:
    """Convenience: the current life story compiled for the system prompt.
    include_sayings=False omits her phrases (the moment's hint carries them)."""
    return load().to_prompt(include_sayings=include_sayings)


def status() -> str:
    ls = load()
    if ls.is_empty():
        return (f"life story: not set ({_file()}). Build it gently with "
                f"`ctwin remember` — one memory at a time.")
    bits = [b for b in [
        ls.people and f"{len(ls.people)} people",
        ls.places and f"{len(ls.places)} places",
        ls.sayings and f"{len(ls.sayings)} sayings",
        ls.stories and f"{len(ls.stories)} memories",
        ls.loves and f"{len(ls.loves)} joys",
        ls.dates and f"{len(ls.dates)} anchors",
    ] if b]
    return f"life story: {', '.join(bits)} — sealed, on-device ({_file()})."


def clear() -> bool:
    path = _file()
    try:
        if path.is_file():
            path.unlink()
            return True
    except OSError:
        pass
    return False


# ---- small, safe adders (used by the guided interview) -----------------------
def add_person(name: str, relation: str = "", note: str = "") -> None:
    ls = load()
    ls.people.append(Person(name=name.strip(), relation=relation.strip(), note=note.strip()))
    save(ls)


def add_saying(saying: str) -> None:
    s = saying.strip()
    if not s:
        return
    ls = load()
    if s not in ls.sayings:
        ls.sayings.append(s)
        save(ls)


def add_story(title: str, text: str, when: str = "") -> None:
    if not text.strip():
        return
    ls = load()
    ls.stories.append(Story(title=title.strip(), text=text.strip(), when=when.strip()))
    save(ls)


def add_place(place: str) -> None:
    p = place.strip()
    if not p:
        return
    ls = load()
    if p not in ls.places:
        ls.places.append(p)
        save(ls)


def add_love(love: str) -> None:
    v = love.strip()
    if not v:
        return
    ls = load()
    if v not in ls.loves:
        ls.loves.append(v)
        save(ls)


def add_date(anchor: str) -> None:
    a = anchor.strip()
    if not a:
        return
    ls = load()
    if a not in ls.dates:
        ls.dates.append(a)
        save(ls)
