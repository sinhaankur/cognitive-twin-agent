"""
Life rhythms — Anita's awareness of *your* day.

She learns, on-device, when you're actually around: your active hours, a likely
sleep window, your work window, and recurring activity patterns (e.g. a commute).
This grows over time from the timestamps already in your private memory — no extra
tracking, nothing uploaded.

Everything is timezone-aware so she never confuses the time. The user can also
state things directly (e.g. "I sleep around 11", "I drive to work at 9"), stored
as overrides.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import stat
from collections import Counter
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


OVERRIDES = "rhythms.json"


# --- timezone (always explicit, never guessed wrong) --------------------------
def now() -> _dt.datetime:
    """Local, timezone-aware now."""
    return _dt.datetime.now().astimezone()


def timezone_line() -> str:
    n = now()
    off = n.utcoffset() or _dt.timedelta(0)
    hrs = off.total_seconds() / 3600
    sign = "+" if hrs >= 0 else "-"
    return (f"It is {n.strftime('%A %H:%M')} {n.tzname()} "
            f"(UTC{sign}{abs(hrs):.0f}). Always use this timezone.")


# --- learn active hours from interaction timestamps ---------------------------
def _active_hours() -> Counter:
    hours: Counter = Counter()
    for e in memory.entries():
        ts = e.get("ts", "")
        try:
            hours[_dt.datetime.fromisoformat(ts).hour] += 1
        except ValueError:
            pass
    return hours


def infer() -> dict[str, Any]:
    """Infer sleep / work windows + active hours from when you interact. Gentle,
    improves with more history."""
    over = _read()
    hours = _active_hours()
    total = sum(hours.values())
    out: dict[str, Any] = {"interactions": total}

    if total >= 8:
        active = sorted(h for h, c in hours.items() if c >= max(1, total * 0.04))
        out["active_hours"] = active
        # quietest 6-hour block ≈ sleep
        if active:
            quietest = min(range(24),
                           key=lambda start: sum(hours.get((start + i) % 24, 0) for i in range(6)))
            out["likely_sleep"] = {"from": quietest, "to": (quietest + 6) % 24}
        # daytime concentration ≈ work
        work = [h for h in active if 8 <= h <= 18]
        if work:
            out["likely_work"] = {"from": min(work), "to": max(work)}

    # user-stated overrides win
    out.update({k: v for k, v in over.items() if v})
    return out


def set_override(key: str, value: Any) -> None:
    """User states a rhythm directly, e.g. set_override('sleep', '23:00')."""
    data = _read()
    data[key] = value
    _write(data)


# --- named daily commitments (the school run, the gym, …) ----------------------
# These are the recurring anchors of a real day that the user TELLS Vera:
# "drop Ritam 8am", "pick up Ritam 4pm", "gym 5:30pm weekdays". Stored sealed,
# read-only reasoning — Vera holds them and reasons around them (reminders,
# "am I free before pickup"), but never acts on its own.
_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _parse_hhmm(s: str) -> str | None:
    import re as _re
    s = (s or "").strip().lower().replace(".", ":")
    m = _re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", s)
    if not m:
        return None
    h = int(m.group(1)); mm = int(m.group(2) or 0); ap = m.group(3)
    if ap == "pm" and h < 12: h += 12
    if ap == "am" and h == 12: h = 0
    if not (0 <= h < 24 and 0 <= mm < 60):
        return None
    return f"{h:02d}:{mm:02d}"


def add_commitment(name: str, time_str: str, days: str = "daily") -> str:
    """Add/update a recurring daily commitment. `days`: 'daily', 'weekdays',
    'weekends', or a comma list like 'mon,wed,fri'."""
    hhmm = _parse_hhmm(time_str)
    if not hhmm:
        return f"I couldn't read the time '{time_str}'. Try like '8am' or '16:30'."
    d = (days or "daily").lower().strip()
    if d == "weekdays":
        day_list = _DAYS[:5]
    elif d == "weekends":
        day_list = _DAYS[5:]
    elif d in ("daily", "everyday", "every day", ""):
        day_list = list(_DAYS)
    else:
        day_list = [x.strip()[:3] for x in d.split(",") if x.strip()[:3] in _DAYS]
        if not day_list:
            day_list = list(_DAYS)
    data = _read()
    coms = data.get("commitments", [])
    coms = [c for c in coms if c.get("name", "").lower() != name.lower()]  # replace same-named
    coms.append({"name": name.strip(), "time": hhmm, "days": day_list})
    coms.sort(key=lambda c: c["time"])
    data["commitments"] = coms
    _write(data)
    when = "every day" if len(day_list) == 7 else ("weekdays" if day_list == _DAYS[:5] else ", ".join(day_list))
    return f"Got it — {name.strip()} at {hhmm}, {when}. I'll keep it in mind."


def list_commitments() -> list[dict[str, Any]]:
    data = _read()
    coms = data.get("commitments", [])
    return coms if isinstance(coms, list) else []


def remove_commitment(name: str) -> str:
    data = _read()
    coms = data.get("commitments", [])
    n = len(coms)
    coms = [c for c in coms if c.get("name", "").lower() != name.lower()]
    data["commitments"] = coms
    _write(data)
    return f"Removed '{name}'." if len(coms) < n else f"No commitment named '{name}'."


def today_commitments() -> list[dict[str, Any]]:
    """Today's commitments, in time order."""
    wd = _DAYS[now().weekday()]
    return [c for c in list_commitments() if wd in c.get("days", [])]


def next_commitment() -> str:
    """The next daily anchor coming up (e.g. Ritam pickup) and how long until."""
    n = now()
    cur = f"{n.hour:02d}:{n.minute:02d}"
    upcoming = [c for c in today_commitments() if c["time"] > cur]
    if not upcoming:
        return "Nothing else scheduled in your day. You're clear."
    c = upcoming[0]
    hh, mm = map(int, c["time"].split(":"))
    mins = (hh * 60 + mm) - (n.hour * 60 + n.minute)
    soon = f"in {mins} min" if mins < 60 else f"in {mins//60}h {mins%60}m"
    return f"Next in your day: {c['name']} at {c['time']} ({soon})."


def day_shape() -> str:
    """A readable line of today's anchors — the shape of the day."""
    coms = today_commitments()
    if not coms:
        return "No fixed commitments on today's calendar of routines."
    parts = [f"{c['time']} {c['name']}" for c in coms]
    return "Today's rhythm: " + " · ".join(parts) + "."


def summary_for_prompt() -> str:
    """A private context line so Anita reasons with your day in mind — when to be
    brief, when not to suggest things, etc."""
    r = infer()
    bits = [timezone_line()]
    if r.get("likely_sleep"):
        s = r["likely_sleep"]
        bits.append(f"You likely sleep around {s['from']:02d}:00–{s['to']:02d}:00 — "
                    f"don't propose tasks then.")
    if r.get("likely_work"):
        w = r["likely_work"]
        bits.append(f"Your work hours look like ~{w['from']:02d}:00–{w['to']:02d}:00.")
    if isinstance(r.get("sleep"), str):
        bits.append(f"You've told me you sleep around {r['sleep']}.")
    if isinstance(r.get("activities"), list) and r["activities"]:
        bits.append("Recurring activities you've mentioned: " + ", ".join(r["activities"]) + ".")
    # Named daily anchors the user set (the school run, gym) — reason around them.
    todays = today_commitments()
    if todays:
        bits.append("Today's anchors: " + "; ".join(f"{c['name']} at {c['time']}" for c in todays) + ".")
    if len(bits) == 1 and r.get("interactions", 0) < 8:
        bits.append("(Still learning your daily rhythm.)")
    return "# YOUR DAY (private, on-device)\n" + " ".join(bits)


def part_of_day() -> str:
    h = now().hour
    if h < 5:   return "late night"
    if h < 12:  return "morning"
    if h < 17:  return "afternoon"
    if h < 21:  return "evening"
    return "night"


# --- json helpers (routed through the security kernel: sealed at rest) ---------
def _read() -> dict[str, Any]:
    from . import security

    data = security.read_state(_dir() / OVERRIDES, default={})
    return data if isinstance(data, dict) else {}


def _write(data: dict[str, Any]) -> None:
    from . import security

    security.write_state(_dir() / OVERRIDES, data)


def status() -> str:
    r = infer()
    parts = [now().strftime("%Z %H:%M")]
    if r.get("likely_sleep"):
        parts.append(f"sleep~{r['likely_sleep']['from']:02d}-{r['likely_sleep']['to']:02d}")
    if r.get("likely_work"):
        parts.append(f"work~{r['likely_work']['from']:02d}-{r['likely_work']['to']:02d}")
    return "rhythms: " + ", ".join(parts) + f" ({r.get('interactions',0)} samples, on-device)"


if __name__ == "__main__":
    print(status())
    print()
    print(summary_for_prompt())
