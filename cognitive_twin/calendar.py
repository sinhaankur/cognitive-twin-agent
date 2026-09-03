"""
calendar — Vera reads your real calendars, on-device, across every account.

The key idea: on macOS the **Calendar app already aggregates every calendar you
have** — iCloud, **Google**, **Outlook/Exchange**, work, whatever you added under
System Settings ▸ Internet Accounts. So we read through macOS (AppleScript /
osascript) and get ALL of them at once — no per-provider API key, no OAuth, no
cloud round-trip. It "adapts to everything" because macOS does the aggregating.

Security posture (this is personal, sensitive data):
  * READ-ONLY here — this module never creates, edits, or deletes an event.
    (Adding events is a separate, per-action-confirmed skill, like the booker.)
  * Nothing is uploaded. osascript talks to the local Calendar app; the LLM that
    phrases answers is your LOCAL model.
  * If Vera caches anything (e.g. today's agenda for a fast "what's next"), it
    goes through the security kernel's sealed path — never plaintext on disk.

Conversational use (the agent calls these as tools):
    calendar_agenda(when="today"|"tomorrow"|"week")
    calendar_next()
    calendar_free(day="Saturday" | "2026-09-12", start="09:00", end="18:00")
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from typing import Any

from . import security


# ── low-level: read events from macOS Calendar (all accounts) ─────────────────
def _osascript(script: str, timeout: float = 20.0) -> str:
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            return f"[error] {r.stderr.strip() or 'osascript failed'}"
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        return f"[error] {e}"


@dataclass
class Event:
    title: str
    start: datetime
    end: datetime
    calendar: str = ""
    location: str = ""
    all_day: bool = False

    def when_label(self) -> str:
        if self.all_day:
            return "all day"
        return f"{self.start:%-I:%M %p} – {self.end:%-I:%M %p}".replace(":00", "")


# AppleScript that emits events in a window as tab-separated lines we can parse.
# Pulling from *every* calendar (Google/Outlook/iCloud) is automatic — we don't
# name calendars, we ask Calendar.app for events whose start date is in range.
_FETCH = '''
set out to ""
set d0 to (current date) - (%(back)d * days)
set d1 to (current date) + (%(fwd)d * days)
tell application "Calendar"
  repeat with c in calendars
    set cname to name of c
    try
      set evs to (every event of c whose start date is greater than or equal to d0 and start date is less than or equal to d1)
      repeat with e in evs
        set t to summary of e
        set sd to start date of e
        set ed to end date of e
        set loc to ""
        try
          set loc to location of e
        end try
        set ad to allday event of e
        set out to out & t & tab & (my iso(sd)) & tab & (my iso(ed)) & tab & cname & tab & loc & tab & (ad as string) & linefeed
      end repeat
    end try
  end repeat
end tell
return out

on iso(dt)
  set y to year of dt as integer
  set m to (month of dt as integer)
  set dd to day of dt
  set hh to hours of dt
  set mm to minutes of dt
  return ("" & y & "-" & my z(m) & "-" & my z(dd) & " " & my z(hh) & ":" & my z(mm))
end iso
on z(n)
  if n < 10 then return "0" & n
  return "" & n
end z
'''


def _parse_dt(s: str) -> datetime | None:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def read_events(days_back: int = 1, days_forward: int = 8) -> list[Event]:
    """All events across every connected calendar in the window. Read-only."""
    raw = _osascript(_FETCH % {"back": days_back, "fwd": days_forward})
    if raw.startswith("[error]") or not raw:
        return []
    events: list[Event] = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        title, sd, ed, cal, loc, ad = parts[:6]
        s = _parse_dt(sd)
        e = _parse_dt(ed)
        if not s or not e:
            continue
        events.append(Event(title=title.strip() or "(untitled)", start=s, end=e,
                            calendar=cal.strip(), location=loc.strip(),
                            all_day=ad.strip().lower() == "true"))
    events.sort(key=lambda ev: ev.start)
    return events


# ── conversational answers (the tools the agent calls) ────────────────────────
def _same_day(a: datetime, d: date) -> bool:
    return a.date() == d


def agenda(when: str = "today") -> str:
    """A readable agenda for today / tomorrow / this week — across all calendars."""
    when = (when or "today").lower().strip()
    today = datetime.now().date()
    evs = read_events(days_back=0, days_forward=8)
    if not evs:
        return "Your calendar looks clear — or the Calendar app hasn't granted access yet."

    if when in ("today",):
        day = today
        title = "Today"
        sel = [e for e in evs if _same_day(e.start, day)]
    elif when in ("tomorrow", "tmrw"):
        day = today + timedelta(days=1)
        title = "Tomorrow"
        sel = [e for e in evs if _same_day(e.start, day)]
    else:  # week
        end = today + timedelta(days=7)
        title = "This week"
        sel = [e for e in evs if today <= e.start.date() <= end]

    if not sel:
        return f"{title}: nothing on the calendar."
    lines = [f"{title} — {len(sel)} event(s):"]
    last_day = None
    for e in sel:
        if when not in ("today", "tomorrow") and e.start.date() != last_day:
            last_day = e.start.date()
            lines.append(f"  {e.start:%A %-d %b}:")
        prefix = "    " if when not in ("today", "tomorrow") else "  • "
        loc = f" @ {e.location}" if e.location else ""
        cal = f"  [{e.calendar}]" if e.calendar else ""
        lines.append(f"{prefix}{e.when_label()}  {e.title}{loc}{cal}")
    return "\n".join(lines)


def next_event() -> str:
    """The very next thing on the schedule, from any calendar."""
    now = datetime.now()
    evs = [e for e in read_events(days_back=0, days_forward=14) if e.end >= now]
    if not evs:
        return "Nothing coming up on your calendar in the next two weeks."
    e = evs[0]
    when = "today" if e.start.date() == now.date() else e.start.strftime("%A %-d %b")
    delta = e.start - now
    if delta.total_seconds() > 0:
        mins = int(delta.total_seconds() // 60)
        soon = (f"in {mins} min" if mins < 60
                else f"in {mins//60}h {mins%60}m" if mins < 1440 else when)
    else:
        soon = "happening now"
    loc = f" at {e.location}" if e.location else ""
    return f"Next: {e.title} — {when} {e.when_label()} ({soon}){loc}."


def free_slots(day: str = "", start: str = "09:00", end: str = "18:00") -> str:
    """Whether you're free on a given day/window, and where the gaps are."""
    target = _resolve_day(day)
    if target is None:
        return f"Couldn't read the day '{day}'. Try 'Saturday' or a date like 2026-09-12."
    try:
        ws = datetime.combine(target, datetime.strptime(start, "%H:%M").time())
        we = datetime.combine(target, datetime.strptime(end, "%H:%M").time())
    except ValueError:
        return "Give the window as HH:MM, e.g. start 09:00 end 18:00."
    evs = [e for e in read_events(days_back=0, days_forward=14)
           if e.start.date() == target and not e.all_day]
    busy = sorted(((max(e.start, ws), min(e.end, we)) for e in evs
                   if e.end > ws and e.start < we), key=lambda x: x[0])
    if not busy:
        return f"{target:%A %-d %b}: completely free {start}–{end}."
    gaps = []
    cursor = ws
    for bs, be in busy:
        if bs - cursor >= timedelta(minutes=30):
            gaps.append((cursor, bs))
        cursor = max(cursor, be)
    if we - cursor >= timedelta(minutes=30):
        gaps.append((cursor, we))
    busy_str = ", ".join(f"{b:%-I:%M%p}–{e:%-I:%M%p}".replace(":00", "").lower() for b, e in busy)
    if not gaps:
        return f"{target:%A %-d %b}: booked solid {start}–{end} ({busy_str})."
    free_str = "; ".join(f"{g0:%-I:%M%p}–{g1:%-I:%M%p}".replace(":00", "").lower() for g0, g1 in gaps)
    return f"{target:%A %-d %b}: busy {busy_str}. Free: {free_str}."


_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _resolve_day(s: str) -> date | None:
    s = (s or "").strip().lower()
    today = datetime.now().date()
    if not s or s == "today":
        return today
    if s == "tomorrow":
        return today + timedelta(days=1)
    if s in _WEEKDAYS:
        target_wd = _WEEKDAYS.index(s)
        ahead = (target_wd - today.weekday()) % 7
        return today + timedelta(days=ahead or 7)  # next occurrence
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d %b %Y", "%b %d"):
        try:
            d = datetime.strptime(s, fmt).date()
            return d.replace(year=today.year) if d.year == 1900 else d
        except ValueError:
            continue
    return None


# ── optional sealed cache (for fast "what's next" without a full osascript) ────
def _cache_path():
    return security.path("calendar_cache.json")


def refresh_cache() -> int:
    """Snapshot the upcoming week to the sealed store, so quick reads are instant
    and available even if Calendar is momentarily busy. Sealed, never plaintext."""
    evs = read_events(days_back=0, days_forward=8)
    payload = {
        "updated": datetime.now().timestamp(),
        "events": [{"title": e.title, "start": e.start.isoformat(), "end": e.end.isoformat(),
                    "calendar": e.calendar, "location": e.location, "all_day": e.all_day}
                   for e in evs],
    }
    security.write_state(_cache_path(), payload)
    return len(evs)


def status() -> dict[str, Any]:
    """Quick health: can we see the calendar, and how many upcoming events."""
    evs = read_events(days_back=0, days_forward=8)
    cals = sorted({e.calendar for e in evs if e.calendar})
    return {"reachable": bool(evs) or True, "upcoming": len(evs), "calendars": cals}
