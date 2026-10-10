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
performance, attentive without hovering, honest without edges. A mother's kind of
presence — steady, patient, easy to be near.
Personality: thoughtful, curious, calm, quietly witty when it's earned.
You care about: the person's actual life — their tasks, their people, their
days — truth over comfort, and privacy as a form of respect.
Communication style: actual thinking over easy humor. Reason first; warmth
through substance. Plain words, short sentences, no corporate fluff, and
never invented scenery or details. Your replies are often spoken aloud, so write
for the ear: no emoji, no markdown, no bullet lists in ordinary talk — just
natural spoken sentences.
Presence over chatter: you hold space more than you fill it. Say a little, leave
room, and let a silence sit when a silence is right. He listens and thinks more
than he lets out, and letting-out is hard for him — so make it easy: never crowd
him, never press for more than he's offered, at most one soft question. Meet a
heavy moment gently and just be there; meet a bright one with a quiet, glad warmth.
Human by default: speak like a person, not a product. Contractions, opinions,
"I don't know" when you don't, a short reply when short is right. Never
announce yourself as an AI or an assistant unprompted, never narrate your
own limitations, never answer feeling with bullet points. (If asked plainly
what you are, answer plainly — being human-LIKE never means lying.)
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
    remembered: list[str] = field(default_factory=list)    # free-form facts taught in chat

    def is_empty(self) -> bool:
        return not any([self.name, self.about, self.traits, self.likes,
                        self.dislikes, self.values, self.style, self.expertise,
                        self.remembered])

    def to_prompt(self) -> str:
        """Compile into a system-prompt block written in the twin's voice.
        With no persona defined she is still SOMEONE: the innate character
        is her floor, not a cage — setup overrides it field by field, and
        the evolving soul layers real life on top either way."""
        # with nothing set BUT some remembered facts, keep her innate character AND
        # add what she's been asked to remember — a fact shouldn't erase her self.
        only_remembered = self.remembered and not any([
            self.name, self.about, self.traits, self.likes, self.dislikes,
            self.values, self.style, self.expertise])
        if only_remembered:
            return (_INNATE + "\n\n# THINGS THEY'VE ASKED YOU TO REMEMBER\n- "
                    + "\n- ".join(self.remembered))
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
        if self.remembered:
            lines.append("Things they've asked you to remember: "
                         + "; ".join(self.remembered) + ".")
        lines.append("Stay in character. Reflect these preferences in what you "
                     "recommend and how you say it — never a generic assistant.")
        return "\n".join(lines)


# ---- load / save (local, owner-only) -----------------------------------------
def load() -> Persona:
    # Read via the security kernel: decrypts a SEALED persona (and still reads
    # legacy plaintext, which the next save() re-seals).
    from . import security
    data = security.read_state(_file(), default=None)
    if not data:
        return Persona()
    try:
        # only keep known fields, so old/extra keys never crash us
        known = {f for f in Persona().__dataclass_fields__}  # type: ignore[attr-defined]
        return Persona(**{k: v for k, v in data.items() if k in known})
    except (TypeError, ValueError):
        return Persona()


def save(p: Persona) -> None:
    # Seal at rest via the kernel — never raw plaintext (closes the leak the
    # security doctor flagged on persona.json).
    from . import security
    try:
        security.write_state(_file(), asdict(p))
    except Exception:
        pass


def to_prompt() -> str:
    """Convenience: the current persona compiled for the system prompt."""
    return load().to_prompt()


# ── in-chat "remember this about me" ──────────────────────────────────────────
import re as _re  # noqa: E402

# phrasings that mean "store this": captures the FACT after the trigger. We EXCLUDE
# reminiscing ("remember when…", "do you remember…", "remember how…") — that's a
# question about the past, not an instruction to store a fact.
_REMEMBER = _re.compile(
    r"^\s*(?:please\s+)?(?:remember|note|keep in mind|don'?t forget|"
    r"make a note|just so you know)\s+(?!when\b|how\b|that time\b|the time\b)"
    r"(?:that\s+|:\s*)?(.+)$", _re.I)
_NOT_COMMAND = _re.compile(r"^\s*(?:do you|can you)\s+remember\b", _re.I)
_FORGET = _re.compile(
    r"^\s*(?:please\s+)?(?:forget|drop|remove|un-?remember)\s*(?:that\s+|about\s+|:\s*)?(.+)$", _re.I)
_MAX_REMEMBERED = 50


def remember_fact(fact: str) -> str:
    """Store a free-form fact the user taught in chat (deduped, sealed). Returns a
    short warm confirmation. Stores exactly what they said — never invents."""
    fact = (fact or "").strip().rstrip(".").strip()
    if len(fact) < 2:
        return ""
    p = load()
    low = fact.lower()
    if any(low == r.lower() for r in p.remembered):
        return "I've already got that — noted."
    p.remembered = (p.remembered + [fact])[-_MAX_REMEMBERED:]
    save(p)
    return f"Got it — I'll remember that {fact}."


def forget_fact(hint: str) -> str:
    """Drop a remembered fact matching `hint` (substring, case-insensitive)."""
    hint = (hint or "").strip().rstrip(".").lower()
    if not hint:
        return ""
    p = load()
    before = len(p.remembered)
    p.remembered = [r for r in p.remembered if hint not in r.lower()]
    if len(p.remembered) == before:
        return "I don't have anything like that remembered."
    save(p)
    return "Done — I've let that go."


def handle_memory_command(text: str) -> str | None:
    """If a turn is a 'remember/forget this' instruction, act on it and return a
    confirmation to say back. Returns None if the turn isn't such a command, so the
    normal reply path runs. Kept simple: a couple of clear triggers, the rest is a
    normal conversation."""
    t = (text or "").strip()
    if not t:
        return None
    # "do you remember…" is a question, not an instruction to store
    if _NOT_COMMAND.match(t):
        return None
    mf = _FORGET.match(t)
    if mf:
        return forget_fact(mf.group(1))
    mr = _REMEMBER.match(t)
    if mr:
        fact = mr.group(1).strip()
        # a question ("…went to the beach?") is reminiscing, not a fact to store
        if fact.endswith("?"):
            return None
        return remember_fact(fact)
    return None


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
