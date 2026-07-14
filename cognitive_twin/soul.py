"""
Anita's soul — the part that makes her *grow*, not just respond.

Two things, both fed by the on-device memory of your conversations:

  1. An **evolving personality**: over time she distils traits and tone from how
     you actually talk with her, and folds them into her persona — so she becomes
     more herself the more you share. Local, private, gradual.

  2. **Background reflection**: even while you're away, she keeps thinking about
     the ideas and projects you've mentioned, and saves a few thoughts for when
     you come back.

Everything stays on-device. State lives next to memory:
  ~/.cognitive-twin/soul.json   (evolving personality)
  ~/.cognitive-twin/reflections.json  (thoughts she's had while you were away)
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import stat
from pathlib import Path
from typing import Any

from . import memory


def _dir() -> Path:
    root = Path(os.environ.get("CTWIN_MEMORY_DIR", Path.home() / ".cognitive-twin"))
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, stat.S_IRWXU)
    except OSError:
        pass
    return root


def _read(name: str) -> dict[str, Any]:
    p = _dir() / name
    try:
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _write(name: str, data: dict[str, Any]) -> None:
    p = _dir() / name
    existed = p.exists()
    try:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if not existed:
            os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass


# --- 1) Evolving personality ---------------------------------------------------
# Cheap, deterministic signal now (interests + how warmly/technically you talk);
# a model can deepen this later. The point is that it *changes* with use.

_WARM_CUES = ("thank", "love", "miss", "appreciate", "please", "feel", "happy", "sad")
_TECH_CUES = ("code", "rust", "api", "build", "deploy", "function", "model", "bug", "design")


def evolve_personality() -> dict[str, Any]:
    """Recompute Anita's evolving traits from accumulated history. Idempotent;
    safe to call periodically."""
    entries = memory.entries()
    prompts = [e.get("prompt", "") for e in entries if e.get("prompt")]
    soul = _read("soul.json")

    interactions = len(prompts)
    text = " ".join(prompts).lower()
    warmth = sum(text.count(c) for c in _WARM_CUES)
    techy = sum(text.count(c) for c in _TECH_CUES)

    topics = memory.patterns().get("topics", [])

    # A gentle, growing self-description. Tone leans to whichever register the
    # relationship actually has.
    tone = "warm and caring" if warmth >= techy else "practical and focused"
    soul.update({
        "interactions": interactions,
        "tone": tone,
        "shared_interests": topics[:6],
        "familiarity": _familiarity(interactions),
        "updated": _dt.datetime.now().isoformat(timespec="seconds"),
    })
    _write("soul.json", soul)
    return soul


def _familiarity(n: int) -> str:
    if n < 5:
        return "just getting to know you"
    if n < 25:
        return "growing familiar with you"
    if n < 100:
        return "knows you well"
    return "deeply familiar with you"


def personality_prompt() -> str:
    """A line folded into the system prompt so her growth shows in how she talks."""
    soul = _read("soul.json")
    if not soul:
        return ""
    bits = [f"You have spoken with this person {soul.get('interactions', 0)} times; "
            f"you are {soul.get('familiarity', 'getting to know them')}."]
    if soul.get("tone"):
        bits.append(f"Your manner with them has become {soul['tone']}.")
    if soul.get("shared_interests"):
        bits.append("Shared ground you keep returning to: "
                    + ", ".join(soul["shared_interests"]) + ".")
    bits.append("Let this relationship show — speak like someone who has been "
                "growing alongside them, not a stranger.")
    return "# WHO YOU'VE BECOME (evolving)\n" + " ".join(bits)


# --- 2) Background reflection (while you're away) ------------------------------

def project_seeds() -> list[str]:
    """What the user has been on about LATELY — reflections must live in the
    present, not orbit whatever dominated the log weeks ago. Terms from the
    last 7 days of memory, falling back to all-time only when recent life is
    too thin to read."""
    cutoff = _dt.datetime.now() - _dt.timedelta(days=7)
    counts: dict[str, int] = {}
    for e in memory.entries(limit=120):
        ts = e.get("ts") or ""
        try:
            if _dt.datetime.fromisoformat(ts) < cutoff:
                continue
        except ValueError:
            continue
        for t in memory._terms(e.get("prompt") or ""):
            counts[t] = counts.get(t, 0) + 1
    recent = [t for t, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:5]]
    return recent if len(recent) >= 2 else memory.patterns().get("topics", [])[:5]


_REFLECTION_FRESH_H = 48.0


def add_reflection(text: str) -> None:
    """Store a thought Anita had while you were away (most recent first,
    capped, dedup-safe — thinking the same thought twice isn't thinking)."""
    text = text.strip()
    data = _read("reflections.json")
    items = data.get("items", [])
    def _same(a: str, b: str) -> bool:
        a, b = a.strip().lower(), b.strip().lower()
        head = min(len(a), len(b), 40)
        return head >= 20 and a[:head] == b[:head]
    if any(_same(i.get("thought") or "", text) for i in items):
        return
    items.insert(0, {
        "ts": _dt.datetime.now().isoformat(timespec="seconds"),
        "thought": text,
    })
    data["items"] = items[:20]
    _write("reflections.json", data)


def pending_reflections(clear: bool = False) -> list[dict[str, Any]]:
    """Thoughts she saved while you were away. Present tense by contract: a
    thought older than ~2 days is no longer "while you were away" — it's a
    nag, and it expires quietly. Optionally clear after reading."""
    data = _read("reflections.json")
    items = data.get("items", [])
    cutoff = _dt.datetime.now() - _dt.timedelta(hours=_REFLECTION_FRESH_H)
    fresh = []
    for i in items:
        try:
            if _dt.datetime.fromisoformat(i.get("ts") or "") >= cutoff:
                fresh.append(i)
        except ValueError:
            continue
    if len(fresh) != len(items):
        _write("reflections.json", {"items": fresh})
    if clear and fresh:
        _write("reflections.json", {"items": []})
    return fresh


def reflection_prompt() -> str:
    """Ask the model (elsewhere) to think about the user's projects. Returns the
    instruction; the caller runs it through the agent and stores the result."""
    seeds = project_seeds()
    if not seeds:
        return ""
    style = ""
    try:
        from . import mood
        style = mood.reflection_style()
    except Exception:
        pass
    return (
        "While the user is away, think about what they've been working on: "
        + ", ".join(seeds)
        + ". Offer ONE single-sentence thought or idea about one of these — the "
        "kind of thing someone who cares about their work would bring up later. "
        "It must be specific and NEW — an angle, a question, a connection — "
        "never a platitude and never a repeat of something already said. "
        "One line only, personal and specific, no preamble." + style
    )


def clear() -> bool:
    """Forget the evolving personality + reflections (user control)."""
    removed = False
    for name in ("soul.json", "reflections.json"):
        p = _dir() / name
        try:
            if p.is_file():
                p.unlink()
                removed = True
        except OSError:
            pass
    return removed


def status() -> str:
    soul = _read("soul.json")
    refl = _read("reflections.json").get("items", [])
    if not soul:
        return "soul: not formed yet (talk with her a few times)"
    return (f"soul: {soul.get('familiarity','')}, manner {soul.get('tone','')}, "
            f"{len(refl)} reflection(s) waiting — on-device")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "evolve":
        print(json.dumps(evolve_personality(), indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "clear":
        print("cleared." if clear() else "nothing to clear.")
    else:
        print(status())
        if personality_prompt():
            print("\n--- who she's become ---")
            print(personality_prompt())
