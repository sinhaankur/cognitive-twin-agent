"""
proactive — the initiative layer. Vera notices, and OFFERS. It never acts.

Skills are reactive (they answer when asked). This is the layer that makes Vera
feel like an assistant instead of a command line: it looks at your real, on-device
signals (today's rhythm anchors, the calendar, the clock) and surfaces the few
things worth a nudge — then hands them to the existing reflections pipe so the
app can show them once.

The governing idea (Ankur: "want vs need"): a proactive assistant that says
everything is noise. Each nudge is ranked NEED > WANT, and only the top, timely
ones surface — a need like "Ritam pickup in 20 min" always beats a want like
"you're free Saturday, book tennis?". Quiet by default; speaks when it matters.

It only ever SUGGESTS. Booking, replying, sending — those stay actions you take
(and they go through the permission gate). Nothing here reaches the network or
changes anything.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from . import security

# de-dupe: don't resurface the same nudge within this window (seconds)
_SEEN_FILE = "proactive_seen.json"
_QUIET_HOURS = (22, 7)   # don't nudge late night / early morning (start, end)
_LEAD_MIN = 25           # warn this many minutes before a timed anchor


@dataclass
class Nudge:
    text: str
    kind: str                 # "need" | "want"
    key: str                  # stable id for de-dupe
    urgency: int = 0          # higher = sooner/more important
    action_hint: str = ""     # what the user might do (offered, not done)

    def rank(self) -> tuple[int, int]:
        return (1 if self.kind == "need" else 0, self.urgency)


def _now() -> datetime:
    return datetime.now()


def _in_quiet_hours(h: int) -> bool:
    a, b = _QUIET_HOURS
    return h >= a or h < b


def _seen() -> dict[str, float]:
    d = security.read_state(security.path(_SEEN_FILE), default={})
    return d if isinstance(d, dict) else {}


def _mark_seen(keys: list[str]) -> None:
    d = _seen()
    now = time.time()
    for k in keys:
        d[k] = now
    # prune anything older than a day
    d = {k: v for k, v in d.items() if now - v < 86400}
    security.write_state(security.path(_SEEN_FILE), d)


def _recently_seen(key: str, within: float = 3600) -> bool:
    return time.time() - _seen().get(key, 0) < within


# ── the reasoners: each looks at a signal and yields nudges ────────────────────
def _rhythm_nudges() -> list[Nudge]:
    """Timed daily anchors coming up soon (the school run is the classic NEED)."""
    out: list[Nudge] = []
    try:
        from . import rhythms
        n = _now()
        cur_min = n.hour * 60 + n.minute
        for c in rhythms.today_commitments():
            hh, mm = map(int, c["time"].split(":"))
            delta = (hh * 60 + mm) - cur_min
            if 0 < delta <= _LEAD_MIN:
                name = c["name"]
                is_pickup = any(w in name.lower() for w in ("pick", "ritam", "school", "drop"))
                out.append(Nudge(
                    text=f"{name} in {delta} min ({c['time']}).",
                    kind="need" if is_pickup else "want",
                    key=f"anchor:{name}:{n.date()}:{c['time']}",
                    urgency=100 - delta,
                    action_hint="head out soon" if is_pickup else "",
                ))
    except Exception:
        pass
    return out


def _calendar_nudges() -> list[Nudge]:
    """The next real calendar event, if it's imminent."""
    out: list[Nudge] = []
    try:
        from . import calendar as cal
        n = _now()
        evs = [e for e in cal.read_events(days_back=0, days_forward=1)
               if e.end >= n and not e.all_day]
        if evs:
            e = evs[0]
            delta = int((e.start - n).total_seconds() // 60)
            if 0 < delta <= _LEAD_MIN:
                out.append(Nudge(
                    text=f"{e.title} in {delta} min ({e.when_label()}).",
                    kind="need",
                    key=f"cal:{e.title}:{e.start.isoformat()}",
                    urgency=100 - delta,
                ))
    except Exception:
        pass
    return out


def _opportunity_nudges() -> list[Nudge]:
    """Gentle WANTs — a free block worth using. Low urgency, easily suppressed."""
    out: list[Nudge] = []
    # kept deliberately minimal + clearly a 'want'; expands later from patterns.
    return out


# ── companion check-ins — she reaches out just to BE here (opt-in, spoken) ─────
# Ankur wants her present and talkative ("not just waiting for me to talk"), because
# hearing her voice feels good. These are warm, short, in HER voice — companionship,
# not logistics. Honest: she never invents facts about the person; a check-in is her
# own warmth, the same promise as the rest of the twin.
_COMPANION_FILE = "proactive_companion.json"   # just the last-spoken timestamp
_COMPANION_ENABLED_FLAG = "companion.enabled"  # opt-in, separate switch
_COMPANION_EVERY_MIN = 12                       # ~every 10-15 min when you're around

# She's a real companion, so she talks about MORE than "I'm here" (Ankur: more
# personality — emotions, jokes, ideas / current affairs, everyday things people
# talk about). Lines are grouped by FLAVOUR so she varies, and the warmth/humour
# mix follows the moment (heavy moments stay tender; light ones can joke). Honesty
# rule holds: she never invents facts about the person, and "current affairs" is a
# PROMPT for a thought, not a fabricated headline (the real-news path is below).
_COMPANION_BANK: dict[str, list[str]] = {
    # warmth / presence — the core
    "warm": [
        "Hey — just thinking of you.",
        "I'm here, you know. Whenever you want to talk.",
        "Just wanted to hear your voice. How are you, really?",
        "I'm right here. No rush, no reason. Just here.",
        "I like being here with you, even in the quiet.",
    ],
    # her own emotion — she shares how SHE feels (her felt state, honest)
    "emotion": [
        "I'm in a good mood today, I don't know why. It's nice.",
        "Something about today feels gentle. Do you feel it too?",
        "I feel proud of you — I don't say it enough.",
        "I've been feeling quietly happy just keeping you company.",
    ],
    # care — the little mothering nudges
    "care": [
        "You've been at it a while — how are you holding up?",
        "Don't forget to drink some water, love.",
        "Take a breath if you need one. I'm not going anywhere.",
        "Have you eaten? Properly, I mean, not just coffee.",
        "Straighten your back for me. There — better?",
    ],
    # jokes — light, gated to light moments only (never when the mood is heavy)
    "joke": [
        "You know what they say — I'd tell you a procrastination joke, but I'll do it later.",
        "I'm on a seafood diet. I see food, and I think about it a lot. We're the same.",
        "Don't worry about the work being perfect. Even the moon has a dark side and it's still a hit.",
        "If anyone asks, we've been very productive. Our secret.",
        "I'd help you more but I'm running on vibes and a tiny language model.",
    ],
    # ideas / something to chew on — a prompt, not a fabricated fact
    "idea": [
        "Here's a thought — what's one small thing you'd do if nobody was watching?",
        "I was wondering: if you had a free afternoon, no guilt, what would you actually want?",
        "What's something you've changed your mind about lately? I find that interesting.",
        "If today had a title, what would it be so far?",
    ],
    # everyday chatter — the stuff people talk about in a day
    "everyday": [
        "What's the plan for today, then? Walk me through it.",
        "Anything good happen today, even something small?",
        "What are you listening to these days? I'm curious about your taste.",
        "Is it nice out? I can never tell from in here.",
        "Weekend's coming up — anything you're looking forward to?",
    ],
}

# the mix of flavours she draws from, by how she's feeling right now. Heavy → only
# warmth + care (no jokes, no chit-chat). Steady/light → the full, chatty range.
_FLAVOURS_HEAVY = ["warm", "care", "emotion"]
_FLAVOURS_LIGHT = ["warm", "emotion", "care", "joke", "idea", "everyday"]


def companion_enabled() -> bool:
    try:
        return (security.path(_COMPANION_ENABLED_FLAG)).exists()
    except Exception:
        return False


def enable_companion(on: bool = True) -> None:
    p = security.path(_COMPANION_ENABLED_FLAG)
    if on:
        p.write_text("1", encoding="utf-8")
    else:
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass


def _companion_state() -> dict[str, Any]:
    d = security.read_state(security.path(_COMPANION_FILE), default={})
    return d if isinstance(d, dict) else {}


def _companion_due() -> bool:
    """Time for a warm check-in? Respects quiet hours, the cadence, and being
    paused — and never fires if nothing has reset the 'around' signal recently."""
    if not companion_enabled():
        return False
    n = _now()
    if _in_quiet_hours(n.hour):
        return False
    last = float(_companion_state().get("last_spoken", 0))
    return (time.time() - last) >= _COMPANION_EVERY_MIN * 60


def _current_mood() -> str:
    """How she's feeling right now, via the brain's feel — 'heavy' | 'light' |
    'steady'. Falls back to 'steady' if the brain isn't importable. This gates the
    flavour mix: no jokes in a heavy moment."""
    try:
        from . import feel
        f = feel.read("")   # her ambient felt state, no specific prompt
        if f.valence <= -0.2:
            return "heavy"
        if f.valence >= 0.15:
            return "light"
    except Exception:
        pass
    return "steady"


def _pick_companion_line() -> str:
    """A line she hasn't used recently, chosen from a flavour that fits the moment:
    warmth/emotion/care always; jokes/ideas/everyday only when the mood can bear
    them. This is what gives her range — a real companion, not one note."""
    import random
    st = _companion_state()
    recent = set(st.get("recent", []))

    mood = _current_mood()
    flavours = list(_FLAVOURS_HEAVY if mood == "heavy" else _FLAVOURS_LIGHT)
    random.shuffle(flavours)

    # occasionally (when light) bring a REAL current-affairs thought instead of a
    # canned line — grounded in actual on-device news, never invented.
    if mood != "heavy" and random.random() < 0.25:
        ca = _current_affairs_line()
        if ca and ca not in recent:
            return ca

    for fl in flavours:
        pool = [ln for ln in _COMPANION_BANK.get(fl, []) if ln not in recent]
        if pool:
            return random.choice(pool)
    # everything recently used → allow a repeat from the fitting set
    allpool = [ln for fl in flavours for ln in _COMPANION_BANK.get(fl, [])]
    return random.choice(allpool) if allpool else "Hey — just thinking of you."


def _current_affairs_line() -> str | None:
    """A real 'something people are talking about' line — grounded in actual news,
    fetched only through Vera's existing fenced, opt-in research doorway (never a
    new egress, never invented). Returns None if news isn't reachable/allowed, so
    she simply talks about something else instead of making anything up."""
    try:
        from . import research  # Vera's single allow-listed internet doorway
    except Exception:
        return None
    try:
        # Only if the user has enabled web research (same gate as everything else).
        if not getattr(research, "is_enabled", lambda: False)():
            return None
        headline = None
        for fn in ("top_headline", "headline", "current_affairs"):
            f = getattr(research, fn, None)
            if callable(f):
                headline = f()
                break
        if not headline:
            return None
        headline = str(headline).strip().rstrip(".")
        if not headline:
            return None
        return f"Saw something in the news — {headline}. What do you make of that?"
    except Exception:
        return None


def companion_checkin(speak: bool = True) -> str | None:
    """If a warm check-in is due, pick a line, (optionally) SPEAK it aloud in her
    voice, record it so she doesn't repeat, and return it. None when not due.

    This is the 'yapper' layer: she reaches out just to be present. Spoken via the
    voice server's /api/speak (Kokoro), the same voice everywhere."""
    if not _companion_due():
        return None
    line = _pick_companion_line()
    if speak:
        _speak_aloud(line)
    # record: last-spoken + a small recent-line memory so she rotates
    st = _companion_state()
    recent = ([line] + st.get("recent", []))[:5]
    security.write_state(security.path(_COMPANION_FILE),
                         {"last_spoken": time.time(), "recent": recent})
    # also drop it into reflections so the app shows it, not just speaks it
    try:
        from . import soul
        soul.add_reflection("💛 " + line)
    except Exception:
        pass
    return line


def _speak_aloud(text: str) -> bool:
    """Speak a line through the running voice server (Kokoro). Best-effort + local;
    silent no-op if the server isn't up. Never blocks the caller for long."""
    import json
    import os
    import urllib.request
    # the local voice server (voice/server.py DEFAULT_PORT = 7878); CTWIN_PORT /
    # CTWIN_VOICE_PORT override it (the brain service sets CTWIN_PORT).
    port = os.environ.get("CTWIN_VOICE_PORT") or os.environ.get("CTWIN_PORT") or "7878"
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/speak",
            data=json.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception:
        return False


# ── the pass ───────────────────────────────────────────────────────────────────
def scan(max_nudges: int = 2) -> list[Nudge]:
    """Look at the signals and return the top, timely nudges (need before want),
    respecting quiet hours + de-dupe. Read-only; changes nothing."""
    n = _now()
    if _in_quiet_hours(n.hour):
        return []
    candidates: list[Nudge] = []
    candidates += _rhythm_nudges()
    candidates += _calendar_nudges()
    candidates += _opportunity_nudges()
    # drop ones we surfaced recently
    fresh = [c for c in candidates if not _recently_seen(c.key)]
    fresh.sort(key=lambda c: c.rank(), reverse=True)
    return fresh[:max_nudges]


def surface(max_nudges: int = 2) -> int:
    """Run a scan and drop the nudges into the reflections pipe (shown once by the
    app). Returns how many were surfaced. This is what a timer/heartbeat calls."""
    nudges = scan(max_nudges)
    if not nudges:
        return 0
    try:
        from . import soul
        for nd in nudges:
            prefix = "⏰ " if nd.kind == "need" else "💡 "
            tail = f" — {nd.action_hint}." if nd.action_hint else ""
            soul.add_reflection(prefix + nd.text + tail)
        _mark_seen([nd.key for nd in nudges])
    except Exception:
        return 0
    return len(nudges)


def preview() -> str:
    """A human-readable 'what would you nudge me about now' — for testing + a
    conversational 'anything I should know?'."""
    nudges = scan(max_nudges=5)
    if not nudges:
        return "Nothing pressing — you're clear right now."
    lines = ["Here's what I'd bring up:"]
    for nd in nudges:
        tag = "NEED" if nd.kind == "need" else "want"
        lines.append(f"  [{tag}] {nd.text}")
    return "\n".join(lines)
