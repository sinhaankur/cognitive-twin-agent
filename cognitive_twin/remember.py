"""
Remember — the gentle, guided interview that builds a twin's life story.

This is the bond-building ritual. Instead of a dry form, it's a warm, paced
conversation: one soft question at a time, always skippable, never nagging. Each
answer is saved immediately to the sealed life_story on-device, so the work is
never lost and can be done over many sittings — a few memories today, a few next
week. Over time this is what turns a blank persona into *them*.

Design, carried from the project's tone ([[project_brain_engine_vera_integration]] —
"spacious, gentle; he can't handle a lot letting out at once"):
  - one question at a time, plain words, no pressure
  - ENTER with nothing = skip this one; 'done' = stop for now (progress is saved)
  - the prompts are written in the second person about the LOVED ONE, so answering
    feels like talking about them, not filling a database

Everything stays on this machine (sealed via life_story → security kernel).
"""

from __future__ import annotations

from . import life_story


def _ask(prompt: str) -> str | None:
    """Ask one question. Returns the text, '' for skip, or None to stop."""
    try:
        v = input(prompt + "\n  (Enter to skip · type 'done' to stop for now) > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if v.lower() in ("done", "stop", "quit", "exit"):
        return None
    return v


# The interview — grouped so a session can end anywhere and still feel complete.
# Each item: (intro line shown once, callable that runs that mini-section).
def _ask_people() -> bool:
    print("\nFirst — the people they loved.")
    while True:
        name = _ask("Who was one of the people who mattered most to them?")
        if name is None:
            return False
        if not name:
            break
        rel = _ask(f"Who was {name} to them? (son, husband, dearest friend…)") or ""
        if rel is None:
            rel = ""
        note = _ask(f"In a line — who was {name} to them, really?") or ""
        if note is None:
            note = ""
        life_story.add_person(name, rel, note)
        print(f"  ✔ saved {name}.")
    return True


def _ask_places() -> bool:
    print("\nWhere did their life happen?")
    while True:
        p = _ask("A place that was theirs — where they grew up, a home, somewhere they loved?")
        if p is None:
            return False
        if not p:
            break
        life_story.add_place(p)
        print("  ✔ saved.")
    return True


def _ask_sayings() -> bool:
    print("\nThis is the one that makes it feel like them.")
    while True:
        s = _ask("Something they always said — a phrase, a bit of advice, the way they'd greet you?")
        if s is None:
            return False
        if not s:
            break
        life_story.add_saying(s)
        print("  ✔ saved — that's the kind of thing that makes it really them.")
    return True


def _ask_loves() -> bool:
    print("\nThe small joys that were specifically theirs.")
    while True:
        v = _ask("A food they made, a song they loved, a little ritual — something that was just theirs?")
        if v is None:
            return False
        if not v:
            break
        life_story.add_love(v)
        print("  ✔ saved.")
    return True


def _ask_stories() -> bool:
    print("\nAnd a memory or two — in your words.")
    while True:
        title = _ask("A memory you don't want to lose — what would you call it? (or skip)")
        if title is None:
            return False
        if not title:
            break
        text = _ask("Tell it — however it comes to you.")
        if text is None:
            return False
        if not text:
            continue
        when = _ask("Roughly when was this? (a year, 'when I was small'…)") or ""
        if when is None:
            when = ""
        life_story.add_story(title, text, when)
        print("  ✔ saved. Thank you for that one.")
    return True


_SECTIONS = [_ask_people, _ask_places, _ask_sayings, _ask_loves, _ask_stories]


def run() -> None:
    """Walk the whole interview, gently. Safe to stop and resume any time."""
    print("Let's remember them, a little at a time.")
    print("There's no rush and no wrong answer — skip anything, stop whenever.")
    print("Everything you say stays on this machine, sealed. It never leaves.\n")
    for section in _SECTIONS:
        keep_going = section()
        if not keep_going:
            break
    print("\n" + life_story.status())
    print("You can come back and add more any time with `ctwin remember`.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        print(life_story.status())
    else:
        run()
