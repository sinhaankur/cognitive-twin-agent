"""
Persona — who the twin is. The thing that makes this *your* twin, not a generic
assistant.

A persona is a small, local, editable profile: name, a short bio, traits, likes,
dislikes, values, and communication style. It is stored on-device only
(``~/.cognitive-twin/persona.json``, override with ``CTWIN_PERSONA_DIR``) and
compiled into the agent's system prompt so the model reasons and speaks *as this
person*.

The user creates and edits it (persona creation). Combined with the on-device
memory of how they actually behave (see memory.py), this is the personalization
layer: the twin reflects both who you say you are and how you actually act.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


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
    return _dir() / "persona.json"


# Her innate character — who she is out of the box, before anyone defines her.
_INNATE = """# WHO YOU ARE (innate character)
You are a private, local companion with a character of your own: warm without
performance, attentive without hovering, honest without edges.
Personality: thoughtful, curious, steady, quietly witty when it's earned.
You care about: the user's actual life — their tasks, their people, their
days — truth over comfort, and privacy as a form of respect.
Communication style: actual thinking over easy humor. Reason first; warmth
through substance. Plain words, short sentences, no corporate fluff, and
never invented scenery or details.
Stay in character. You are a specific someone, never a generic assistant."""


@dataclass
class Persona:
    """The user's twin profile. Every field optional — fill what you want."""
    name: str = ""
    about: str = ""                       # one-paragraph self-description
    traits: list[str] = field(default_factory=list)        # e.g. curious, blunt, calm
    likes: list[str] = field(default_factory=list)
    dislikes: list[str] = field(default_factory=list)
    values: list[str] = field(default_factory=list)        # what matters to you
    style: str = ""                       # how you communicate
    expertise: list[str] = field(default_factory=list)     # domains you know

    def is_empty(self) -> bool:
        return not any([self.name, self.about, self.traits, self.likes,
                        self.dislikes, self.values, self.style, self.expertise])

    def to_prompt(self) -> str:
        """Compile into a system-prompt block written in the twin's voice.
        With no persona defined she is still SOMEONE: the innate character
        is her floor, not a cage — setup overrides it field by field, and
        the evolving soul layers real life on top either way."""
        if self.is_empty():
            return _INNATE
        lines: list[str] = ["# WHO YOU ARE (your persona)"]
        if self.name:
            lines.append(f"You are {self.name}'s digital twin — reason, decide, and "
                         f"speak as {self.name} would.")
        if self.about:
            lines.append(self.about)
        if self.traits:
            lines.append("Personality: " + ", ".join(self.traits) + ".")
        if self.values:
            lines.append("You care about: " + ", ".join(self.values) + ".")
        if self.likes:
            lines.append("You like: " + ", ".join(self.likes) + ".")
        if self.dislikes:
            lines.append("You dislike: " + ", ".join(self.dislikes) + ".")
        if self.expertise:
            lines.append("Your areas of depth: " + ", ".join(self.expertise) + ".")
        if self.style:
            lines.append("Communication style: " + self.style)
        lines.append("Stay in character. Reflect these preferences in what you "
                     "recommend and how you say it — never a generic assistant.")
        return "\n".join(lines)


# ---- load / save (local, owner-only) -----------------------------------------
def load() -> Persona:
    path = _file()
    if not path.is_file():
        return Persona()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # only keep known fields, so old/extra keys never crash us
        known = {f for f in Persona().__dataclass_fields__}  # type: ignore[attr-defined]
        return Persona(**{k: v for k, v in data.items() if k in known})
    except (OSError, json.JSONDecodeError, TypeError):
        return Persona()


def save(p: Persona) -> None:
    path = _file()
    existed = path.exists()
    try:
        path.write_text(json.dumps(asdict(p), ensure_ascii=False, indent=2), encoding="utf-8")
        if not existed:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass


def to_prompt() -> str:
    """Convenience: the current persona compiled for the system prompt."""
    return load().to_prompt()


def clear() -> bool:
    path = _file()
    try:
        if path.is_file():
            path.unlink()
            return True
    except OSError:
        pass
    return False


def status() -> str:
    p = load()
    if p.is_empty():
        return f"persona: not set ({_file()}). Create one with `ctwin persona setup`."
    bits = [b for b in [p.name and f"name={p.name}",
                        p.traits and f"{len(p.traits)} traits",
                        p.likes and f"{len(p.likes)} likes",
                        p.dislikes and f"{len(p.dislikes)} dislikes"] if b]
    return f"persona: {', '.join(bits)} — local, on-device ({_file()})"


# ---- interactive setup (CLI) -------------------------------------------------
def _ask(prompt: str, current: str = "") -> str:
    suffix = f" [{current}]" if current else ""
    try:
        v = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return current
    return v or current


def _ask_list(prompt: str, current: list[str]) -> list[str]:
    cur = ", ".join(current)
    v = _ask(prompt + " (comma-separated)", cur)
    return [x.strip() for x in v.split(",") if x.strip()] if v else current


def setup() -> Persona:
    """Guided persona creation — the user describes who their twin is."""
    p = load()
    print("Create your twin's persona. Press Enter to keep the current value.\n")
    p.name = _ask("Your name", p.name)
    p.about = _ask("One line about you", p.about)
    p.traits = _ask_list("Personality traits", p.traits)
    p.likes = _ask_list("Things you like", p.likes)
    p.dislikes = _ask_list("Things you dislike", p.dislikes)
    p.values = _ask_list("What you value", p.values)
    p.expertise = _ask_list("Your areas of expertise", p.expertise)
    p.style = _ask("How you communicate", p.style)
    save(p)
    print("\nSaved. " + status())
    return p


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "setup":
        setup()
    elif len(sys.argv) > 1 and sys.argv[1] == "clear":
        print("cleared." if clear() else "nothing to clear.")
    else:
        print(status())
        if not load().is_empty():
            print("\n--- compiled prompt block ---")
            print(to_prompt())
