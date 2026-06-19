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


# --- json helpers --------------------------------------------------------------
def _read() -> dict[str, Any]:
    p = _dir() / OVERRIDES
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write(data: dict[str, Any]) -> None:
    p = _dir() / OVERRIDES
    existed = p.exists()
    try:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if not existed:
            os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


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
