"""
Keepsakes — the things taught FOR KEEPS, kept whole, forever.

Everyday conversation is logged lightly (memory.py truncates each turn to ~240
chars — fine for "what did we talk about", wrong for a *story*). A keepsake is
different: something you deliberately hand to Vera to carry and pass on — a whole
memory of your mother, a lesson for your son, who someone was, a thing you never
want lost. So keepsakes are:

  • WHOLE   — stored in full, never truncated.
  • FOREVER — append-only, never pruned, never expired. The log only grows.
  • SEALED  — on-device, owner-only (security kernel), never uploaded.
  • FOR SOMEONE — optionally tagged "for" (e.g. your son) and "about" (e.g. Mom),
                  so one day the right person can find the right keepsakes.
  • CARRIED — the relevant ones fold into Vera's prompt, so she speaks FROM them.

This is the inheritance core: the part of Vera meant to outlast the moment, and
eventually the keeper — a library of who you are and who they were, kept for the
people who come after. Built to be trusted: nothing you put here goes away.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass
from typing import Any

from . import security

_LOG = "keepsakes.jsonl"        # sealed, append-only


@dataclass
class Keepsake:
    id: str
    text: str                   # the whole thing — never truncated
    title: str = ""             # a short name, optional
    about: str = ""             # who/what it's about ("my mother", "home")
    for_whom: str = ""          # who it's for ("my son", "the family")
    kind: str = "memory"        # memory | lesson | story | who | saying | wish
    ts: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "text": self.text, "title": self.title,
            "about": self.about, "for": self.for_whom, "kind": self.kind,
            "ts": self.ts,
        }


def _path():
    return security.path(_LOG)


# ── write (sealed, append-only — the log only GROWS) ────────────────────────────
def keep(text: str, *, title: str = "", about: str = "", for_whom: str = "",
         kind: str = "memory") -> Keepsake | None:
    """Keep something WHOLE, forever. No truncation, no pruning. Returns the saved
    Keepsake, or None if there's genuinely nothing to keep."""
    text = (text or "").strip()
    if not text:
        return None
    ks = Keepsake(
        id=uuid.uuid4().hex[:12],
        text=text,
        title=title.strip(),
        about=about.strip(),
        for_whom=for_whom.strip(),
        kind=(kind or "memory").strip().lower(),
        ts=_dt.datetime.now().isoformat(timespec="seconds"),
    )
    security.append_line(_path(), ks.to_dict())
    return ks


# ── read (unsealed on THIS device only) ─────────────────────────────────────────
def all_keepsakes() -> list[Keepsake]:
    """Every keepsake, oldest → newest. Nothing is ever dropped."""
    rows = security.read_lines(_path())
    out: list[Keepsake] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        out.append(Keepsake(
            id=r.get("id", ""), text=r.get("text", ""), title=r.get("title", ""),
            about=r.get("about", ""), for_whom=r.get("for", ""),
            kind=r.get("kind", "memory"), ts=r.get("ts", ""),
        ))
    return out


def count() -> int:
    return len(all_keepsakes())


def status() -> str:
    ks = all_keepsakes()
    if not ks:
        return "No keepsakes yet. Tell Vera something to keep — a memory, a lesson, who someone was."
    kinds: dict[str, int] = {}
    for k in ks:
        kinds[k.kind] = kinds.get(k.kind, 0) + 1
    bits = ", ".join(f"{n} {k}{'s' if n != 1 else ''}" for k, n in sorted(kinds.items()))
    return f"{len(ks)} keepsake{'s' if len(ks) != 1 else ''} kept whole, forever ({bits})."


# ── carry (fold into her prompt, so she speaks FROM them) ───────────────────────
def to_prompt(query: str = "", k: int = 3, max_chars: int = 2400) -> str:
    """The keepsakes most worth carrying into THIS turn. Whole keepsakes are long,
    so we include the few most relevant (by simple word overlap with the turn, else
    the most recent), under a character budget — the full text, never a summary.

    A tiny, transparent relevance pass (no model, no embedding): keep it honest and
    cheap. When nothing is asked, carry the most recent — the latest thing you chose
    to hand her stays close."""
    ks = all_keepsakes()
    if not ks:
        return ""
    q = {w for w in _words(query)} if query else set()
    if q:
        def score(x: Keepsake) -> int:
            hay = _words(f"{x.title} {x.about} {x.for_whom} {x.text}")
            return len(q & set(hay))
        ranked = sorted(ks, key=lambda x: (score(x), x.ts), reverse=True)
        ranked = [x for x in ranked if score(x) > 0] or ks[-k:]
    else:
        ranked = list(reversed(ks))      # most recent first

    lines: list[str] = []
    used = 0
    for x in ranked[:k]:
        head = x.title or (x.about and f"about {x.about}") or x.kind
        tag = []
        if x.about:
            tag.append(f"about {x.about}")
        if x.for_whom:
            tag.append(f"for {x.for_whom}")
        meta = f" ({'; '.join(tag)})" if tag else ""
        block = f"— {head}{meta}:\n{x.text}"
        if used + len(block) > max_chars:
            break
        lines.append(block)
        used += len(block)
    if not lines:
        return ""
    return ("# KEPT FOR KEEPS (things you were deliberately given to carry and "
            "pass on — speak from these as true, they are not to be forgotten)\n"
            + "\n\n".join(lines))


def _words(s: str) -> list[str]:
    import re
    return [w for w in re.findall(r"[a-z]{3,}", (s or "").lower())]
