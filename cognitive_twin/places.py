"""
places — where you actually go, so Vera knows your life, not just your screen.

The point (in Ankur's words): the twin feels generic until it knows *what's
happening* — where you went today, where you spend your days, the rhythm of your
real movement. This module gives Vera that, the same way ``activity.py`` gives her
your on-device work patterns: quietly, on-device, and only with your say-so.

One place-log, many sources. Whatever the source — Google Takeout Timeline, the
macOS Significant-Locations store, an iOS Shortcut, or this Mac's live Core
Location — it lands as the same ``Visit`` record and is appended to one sealed
log. So "where did I go today?" has a single answer no matter where the data came
from.

Privacy is the whole point, and it is not negotiable:
  - OFF by default. You opt in (``enable()``).
  - PRIVATE / SNOOZE hard-stops all intake — nothing is read or written while on.
  - Every visit line is sealed at rest with Vera's device-bound key
    (``vault.py`` — ChaCha20-Poly1305, key in the macOS Keychain bound to THIS
    Mac + THIS account). Copy the file off this machine and it reads as noise.
  - It lives in ``~/.cognitive-twin/places.jsonl``, owner-only. Never uploaded.
    Clear it any time (``clear()``).

CLI:
    python3 -m cognitive_twin.places today
    python3 -m cognitive_twin.places week
    python3 -m cognitive_twin.places status
    python3 -m cognitive_twin.places enable | pause | resume | clear

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


# ── storage location (mirrors activity.py) ─────────────────────────────────────
def _home() -> Path:
    root = Path(os.environ.get("CTWIN_MEMORY_DIR", Path.home() / ".cognitive-twin"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _log_path() -> Path:
    return _home() / "places.jsonl"


def _flag_path(name: str) -> Path:
    return _home() / f"places.{name}"


# ── opt-in + private/snooze gates (same contract as activity.py) ───────────────
def enable() -> None:
    _flag_path("enabled").write_text("1", encoding="utf-8")


def disable() -> None:
    _flag_path("enabled").unlink(missing_ok=True)


def is_enabled() -> bool:
    return _flag_path("enabled").is_file()


def pause() -> None:
    """Hard-stop intake until resume(). Nothing is read or stored while paused."""
    _flag_path("paused").write_text("1", encoding="utf-8")


def snooze(minutes: int) -> None:
    until = _dt.datetime.now() + _dt.timedelta(minutes=max(1, minutes))
    _flag_path("paused").write_text(until.isoformat(), encoding="utf-8")


def resume() -> None:
    _flag_path("paused").unlink(missing_ok=True)


def is_paused() -> bool:
    p = _flag_path("paused")
    if not p.is_file():
        return False
    val = p.read_text(encoding="utf-8").strip()
    if val in ("1", ""):
        return True
    try:  # a snooze-until timestamp
        return _dt.datetime.now() < _dt.datetime.fromisoformat(val)
    except ValueError:
        return True


def _intake_allowed() -> bool:
    return is_enabled() and not is_paused()


# ── the one record every source produces ───────────────────────────────────────
@dataclass
class Visit:
    """A place you were, over a span of time. Times are ISO-8601 local strings."""
    place: str                    # human name ("Home", "Equinox Bay St", or an address)
    start: str                    # arrival, ISO-8601
    end: str | None = None        # departure, ISO-8601 (None = ongoing / point sample)
    lat: float | None = None
    lon: float | None = None
    source: str = "unknown"       # "google-timeline" | "apple-significant" | "ios-shortcut" | "core-location"
    category: str | None = None   # optional ("gym", "work", "restaurant") if the source gives one
    confidence: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def day(self) -> str:
        return self.start[:10]


# ── append (sealed) ────────────────────────────────────────────────────────────
def record(visit: Visit) -> bool:
    """Append one sealed visit line, IF intake is enabled and not paused.
    Returns True if written. Sources call this; they must not write the file
    directly, so the privacy gates are always honoured."""
    if not _intake_allowed():
        return False
    return _append_sealed(visit)


def import_visits(visits: Iterable[Visit], *, dedupe: bool = True) -> int:
    """Bulk-append from an importer (Takeout, Apple store, …). Honours the gates.
    De-dupes against place+start so re-importing the same export is idempotent."""
    if not _intake_allowed():
        return 0
    existing = {(v.place, v.start) for v in read_all()} if dedupe else set()
    n = 0
    for v in visits:
        if dedupe and (v.place, v.start) in existing:
            continue
        if _append_sealed(v):
            existing.add((v.place, v.start))
            n += 1
    return n


def _append_sealed(visit: Visit) -> bool:
    # Route through the security kernel — the one guarded, always-sealed path.
    from . import security

    security.append_line(_log_path(), asdict(visit))
    return True


# ── read (unsealed on this device only) ────────────────────────────────────────
def read_all() -> list[Visit]:
    from . import security

    out: list[Visit] = []
    for data in security.read_lines(_log_path()):
        try:
            out.append(Visit(**data))
        except Exception:
            continue  # skip a foreign/corrupt record rather than fail the read
    return out


def clear() -> None:
    _log_path().unlink(missing_ok=True)


# ── queries: the questions Vera actually gets asked ────────────────────────────
def visits_on(day: str) -> list[Visit]:
    """All visits whose start date == day (YYYY-MM-DD), in time order."""
    return sorted((v for v in read_all() if v.day() == day), key=lambda v: v.start)


def today(now: _dt.datetime | None = None) -> list[Visit]:
    d = (now or _dt.datetime.now()).date().isoformat()
    return visits_on(d)


def week(now: _dt.datetime | None = None) -> dict[str, list[Visit]]:
    now = now or _dt.datetime.now()
    by_day: dict[str, list[Visit]] = {}
    start = now.date() - _dt.timedelta(days=6)
    for v in read_all():
        try:
            d = _dt.date.fromisoformat(v.day())
        except ValueError:
            continue
        if start <= d <= now.date():
            by_day.setdefault(v.day(), []).append(v)
    for day in by_day:
        by_day[day].sort(key=lambda v: v.start)
    return dict(sorted(by_day.items()))


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in km — used to summarise how far you moved."""
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


# ── human summary (what Vera says back) ────────────────────────────────────────
def _fmt_time(iso: str) -> str:
    try:
        return _dt.datetime.fromisoformat(iso).strftime("%-I:%M %p")
    except ValueError:
        return iso[11:16] if len(iso) >= 16 else iso


def summarize_day(visits: list[Visit], *, label: str = "today") -> str:
    if not is_enabled():
        return ("I'm not tracking your places yet — turn it on with "
                "`python3 -m cognitive_twin.places enable` and connect a source "
                "(Google Timeline export, Apple locations, or the iOS shortcut).")
    if not visits:
        return f"I don't have any places logged for {label} yet."
    lines = [f"Where you went {label}:"]
    dist = 0.0
    prev: tuple[float, float] | None = None
    for v in visits:
        when = _fmt_time(v.start) + (f"–{_fmt_time(v.end)}" if v.end else "")
        tag = f" · {v.category}" if v.category else ""
        lines.append(f"  • {when} — {v.place}{tag}")
        if v.lat is not None and v.lon is not None:
            if prev is not None:
                dist += haversine_km(prev, (v.lat, v.lon))
            prev = (v.lat, v.lon)
    if dist > 0.05:
        lines.append(f"  (~{dist:.1f} km across {len(visits)} stop(s))")
    return "\n".join(lines)


def status() -> str:
    n = len(read_all()) if _log_path().is_file() else 0
    state = "on" if is_enabled() else "off"
    if is_paused():
        state += " (paused)"
    return (f"Places: {state}. {n} visit(s) logged, sealed to this Mac. "
            f"Log: {_log_path()}")


# ── CLI ─────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "enable":
        enable(); print("✓ Places tracking on (opt-in). Connect a source next."); return 0
    if cmd == "disable":
        disable(); print("✓ Places tracking off."); return 0
    if cmd == "pause":
        pause(); print("⏸ Paused — no location is read or stored until resume."); return 0
    if cmd == "resume":
        resume(); print("▶ Resumed."); return 0
    if cmd == "clear":
        clear(); print("✓ Cleared the local places log."); return 0
    if cmd == "status":
        print(status()); return 0
    if cmd == "today":
        print(summarize_day(today(), label="today")); return 0
    if cmd == "week":
        wk = week()
        if not is_enabled():
            print(summarize_day([], label="this week")); return 0
        if not wk:
            print("No places logged in the last 7 days yet."); return 0
        for day, vs in wk.items():
            print(summarize_day(vs, label=day)); print()
        return 0
    print("usage: python3 -m cognitive_twin.places "
          "[today|week|status|enable|pause|resume|clear]")
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
