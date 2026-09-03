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
