"""
mental_model — a living model of the PERSON Vera is with.

The Companion Charter (§3) says she remembers who you are and what you're going
through, and grows from knowing you — a real person doesn't reset every
conversation. This is the hippocampus's substrate: the durable, updated-each-turn
picture of the person that grounds every reply.

Distinct from the neighbours:
  - persona.py : editable, mostly-static facts the USER sets (name, role, values).
  - soul.py    : who VERA is becoming (her side of the relationship).
  - memory     : the raw interaction log (every turn).
  - mental_model (this): Vera's synthesised, current understanding of the PERSON —
    what's alive for them NOW, the threads across days, recurring feelings — built
    from the turns, not typed in.

Principles (charter-aligned):
  - Her own logic, not a model. Updates are deterministic + inspectable (no LLM in
    the loop) so what she "knows" is honest and auditable.
  - Sealed. All state goes through the security kernel (write_state/read_state),
    never a bare file. Owner-only, on-device.
  - Honest. She only records what the turns actually show. No invented backstory.
"""
from __future__ import annotations

import re
import time
from typing import Any

from . import security

_STORE = "mental_model.json"  # sealed under the memory root via security.path()

# How many active threads we keep. A real person tracks a handful of live things,
# not an infinite list — old, untouched threads fade (see _decay).
_MAX_THREADS = 12
_THREAD_TTL_DAYS = 30.0

# Feeling cues → a small, honest emotion vocabulary. Deterministic, readable — the
# charter forbids letting a model decide what she "knows" you feel.
_FEELINGS = {
    "lonely": r"\b(lonely|alone|isolated|no one|nobody)\b",
    "overwhelmed": r"\b(overwhelmed|too much|can'?t cope|drowning|swamped)\b",
    "anxious": r"\b(anxious|worried|scared|afraid|nervous|on edge)\b",
    "sad": r"\b(sad|down|low|blue|crying|tears|hurt)\b",
    "grief": r"\b(miss(ing)?|grief|grieving|passed away|lost (my|her|him)|since (she|he) (died|passed))\b",
    "tired": r"\b(tired|exhausted|drained|burnt out|worn out|no energy)\b",
    "stressed": r"\b(stressed|pressure|deadline|so much to do)\b",
    "hopeful": r"\b(hopeful|excited|looking forward|can'?t wait)\b",
    "proud": r"\b(proud|accomplished|finished|achieved|did it|nailed it)\b",
    "grateful": r"\b(grateful|thankful|appreciate|means a lot)\b",
}

# People the person mentions in a relational way — so she can hold the cast of a
# real life (family, friends). Captures a name after a relationship word.
_PEOPLE = re.compile(
    r"\b(my\s+(mother|mom|mum|father|dad|wife|husband|partner|son|daughter|"
    r"sister|brother|friend|boss|colleague|dog|cat))\b", re.IGNORECASE)

# PERSONALITY cues — how THIS person communicates + what they're drawn to, read
# from how they chat (Ankur: "the way I chat, you understand my personality — cater
# to that so the LLM knows who I am"). Observed, never invented; each is a light
# signal counted over time, and the strongest become a "who they are" line in the
# prompt. Kept simple on purpose (a small, legible map, not a profiler).
_PERSONALITY = {
    # communication style
    "direct": re.compile(r"\b(just|honestly|basically|straight up|cut to|no bs|bottom line)\b", re.I),
    "curious": re.compile(r"\?|^(why|how|what if|wonder|curious)\b", re.I),
    "playful": re.compile(r"\b(haha|lol|lmao|😂|😄|jk|kidding)\b|!{2,}", re.I),
    "reflective": re.compile(r"\b(i think|i feel|i believe|i realised|realized|wonder|meaning|lately)\b", re.I),
    "driven": re.compile(r"\b(build|ship|launch|goal|want to|let's|lets go|make|create|push)\b", re.I),
    "big-picture": re.compile(r"\b(vision|future|overall|the point|ultimately|in the end|so on)\b", re.I),
    # what they care about (interests)
    "tech/AI": re.compile(r"\b(ai|llm|model|code|app|engine|build|rag|neural|data|software)\b", re.I),
    "space/science": re.compile(r"\b(space|universe|satellite|planet|star|physics|science|math)\b", re.I),
    "world/news": re.compile(r"\b(news|war|politics|country|india|world|economy|climate)\b", re.I),
    "family/people": re.compile(r"\b(family|mother|mom|father|son|wife|friend|people|loved)\b", re.I),
    "design/craft": re.compile(r"\b(design|craft|beautiful|aesthetic|art|visual|clean|polish)\b", re.I),
}

# Topic/thread seeds — what a turn is *about* beyond the feeling. Light, honest.
_STOP = set("i you the a an to of and is it im i'm that this me my we so are was for "
            "on in with feel feeling really just about have has had do does my mine "
            "at be been being can could would should will now today".split())


def _now() -> float:
    return time.time()


def _blank() -> dict[str, Any]:
    return {"feelings": {}, "people": {}, "threads": [], "personality": {},
            "updated": None, "turns": 0}


def load() -> dict[str, Any]:
    data = security.read_state(security.path(_STORE), default=None)
    return data if isinstance(data, dict) else _blank()


def _save(data: dict[str, Any]) -> None:
    security.write_state(security.path(_STORE), data)


def _content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z']+", text.lower())
            if w not in _STOP and len(w) > 3]


def _decay(threads: list[dict[str, Any]], now: float) -> list[dict[str, Any]]:
    """Drop threads untouched beyond the TTL; keep the most recent _MAX_THREADS."""
    cutoff = now - _THREAD_TTL_DAYS * 86400
    live = [t for t in threads if t.get("last", 0) >= cutoff]
    live.sort(key=lambda t: t.get("last", 0), reverse=True)
    return live[:_MAX_THREADS]


def observe(text: str) -> dict[str, Any]:
    """Update the model from ONE turn by the person. Deterministic; returns the
    updated model. Call this on real user turns (not scripted/internal ones)."""
    t = (text or "").strip()
    data = load()
    if not t:
        return data
    now = _now()

    # feelings — count occurrences over time (recency-weighted by last-seen)
    for name, pat in _FEELINGS.items():
        if re.search(pat, t, re.IGNORECASE):
            f = data["feelings"].get(name, {"count": 0, "last": 0})
            f["count"] += 1
            f["last"] = now
            data["feelings"][name] = f

    # people — remember who shows up in their life
    for m in _PEOPLE.finditer(t):
        who = m.group(1).lower().replace("my ", "").strip()
        p = data["people"].get(who, {"count": 0, "last": 0})
        p["count"] += 1
        p["last"] = now
        data["people"][who] = p

    # threads — the live things they keep coming back to. Merge into an existing
    # thread if it shares content words, else start a new one.
    words = set(_content_words(t))
    if words:
        merged = False
        for th in data["threads"]:
            if len(words & set(th.get("words", []))) >= 2:
                th["words"] = list(set(th.get("words", [])) | words)[:12]
                th["last"] = now
                th["hits"] = th.get("hits", 1) + 1
                th["gist"] = t[:140]
                merged = True
                break
        if not merged:
            data["threads"].append(
                {"words": list(words)[:12], "gist": t[:140], "hits": 1,
                 "first": now, "last": now})
    data["threads"] = _decay(data["threads"], now)

    # personality — how they communicate + what they're drawn to. Count each cue
    # that fires; the strongest, steadiest traits become "who they are" for the LLM.
    pers = data.get("personality", {})
    for trait, pat in _PERSONALITY.items():
        if pat.search(t):
            p = pers.get(trait, {"count": 0, "last": 0})
            p["count"] += 1
            p["last"] = now
            pers[trait] = p
    data["personality"] = pers

    data["turns"] = data.get("turns", 0) + 1
    data["updated"] = now
    _save(data)
    return data


# traits only count once they've shown up enough to be real (not a one-off word).
_PERSONALITY_MIN = 3


def personality_profile(k: int = 5) -> list[str]:
    """The person's strongest observed traits/interests, most-seen first — only the
    ones seen enough times to be real. Empty until she's learned a few."""
    pers = load().get("personality", {})
    strong = [(name, v) for name, v in pers.items() if v.get("count", 0) >= _PERSONALITY_MIN]
    strong.sort(key=lambda kv: (kv[1].get("count", 0), kv[1].get("last", 0)), reverse=True)
    return [name for name, _ in strong[:k]]


def _recent_feelings(data: dict[str, Any], k: int = 3) -> list[str]:
    items = sorted(data.get("feelings", {}).items(),
                   key=lambda kv: (kv[1].get("last", 0), kv[1].get("count", 0)),
                   reverse=True)
    return [name for name, _ in items[:k]]


def context_for_prompt(max_threads: int = 3) -> str:
    """The hippocampus 'what I know about them right now' fragment, fed into the
    system prompt each turn. Empty string when the model is still blank (honest —
    she doesn't pretend to know someone she's just met)."""
    data = load()
    if not data.get("turns"):
        return ""
    bits: list[str] = []

    # WHO THEY ARE — their personality, learned from how they chat, so the model's
    # replies fit THEM (not a generic user). Observed, never flattering invention.
    traits = personality_profile()
    if traits:
        bits.append("who they are (how they come across): " + ", ".join(traits)
                    + " — meet them there, but don't just mirror them: knowing them "
                    "is for warmth and fit, never an echo chamber. Still offer other "
                    "angles and gently widen their view when it helps.")

    feelings = _recent_feelings(data)
    if feelings:
        bits.append("lately they've been feeling: " + ", ".join(feelings))

    people = sorted(data.get("people", {}).items(),
                    key=lambda kv: kv[1].get("count", 0), reverse=True)[:4]
    if people:
        bits.append("people in their life they mention: "
                    + ", ".join(who for who, _ in people))

    threads = sorted(data.get("threads", []),
                     key=lambda th: (th.get("hits", 0), th.get("last", 0)),
                     reverse=True)[:max_threads]
    if threads:
        lines = "; ".join(f'"{th["gist"]}"' for th in threads)
        bits.append("things that keep coming up for them: " + lines)

    if not bits:
        return ""
    return ("# WHAT YOU KNOW ABOUT THEM (your own memory — use it gently, never "
            "recite it back like a file; let it inform how you're present)\n- "
            + "\n- ".join(bits))


def status() -> str:
    data = load()
    return (f"mental model · turns={data.get('turns', 0)} · "
            f"feelings={len(data.get('feelings', {}))} · "
            f"people={len(data.get('people', {}))} · "
            f"threads={len(data.get('threads', []))}")


def clear() -> bool:
    """Forget everything about the person (owner action)."""
    p = security.path(_STORE)
    if p.is_file():
        p.unlink()
        return True
    return False
