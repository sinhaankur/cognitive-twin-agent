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


# ── movement analysis over the WHOLE history ──────────────────────────────────
# "understand my movement, which places I've been" — not just today/this week,
# but the shape of it across everything logged: the places you return to, how
# far you range, how your movement is distributed. All derived from the sealed
# log on this device; nothing inferred that the data doesn't support.
def _dwell_hours(v: "Visit") -> float:
    """Hours spent at a visit, if both ends are known (else 0 — a point sample)."""
    if not v.end:
        return 0.0
    try:
        s = _dt.datetime.fromisoformat(v.start)
        e = _dt.datetime.fromisoformat(v.end)
        return max(0.0, (e - s).total_seconds() / 3600.0)
    except ValueError:
        return 0.0


@dataclass
class PlaceStat:
    """One place you return to, aggregated across all time."""
    place: str
    visits: int
    hours: float                  # total dwell time (0 if the source gave no spans)
    first: str                    # earliest visit day (YYYY-MM-DD)
    last: str                     # most recent visit day
    lat: float | None = None
    lon: float | None = None
    category: str | None = None


def top_places(limit: int = 12, *, since_days: int | None = None) -> list[PlaceStat]:
    """The places you go to most, across all logged history (or the last
    `since_days`). Ranked by visit count, then by total dwell time — the spots
    that actually anchor your life float to the top."""
    visits = read_all()
    if since_days is not None:
        cutoff = _dt.date.today() - _dt.timedelta(days=max(1, since_days))
        visits = [v for v in visits if _safe_day(v) and _safe_day(v) >= cutoff]
    agg: dict[str, PlaceStat] = {}
    for v in visits:
        key = (v.place or "").strip() or "(unnamed stop)"
        st = agg.get(key)
        if st is None:
            agg[key] = PlaceStat(place=key, visits=1, hours=_dwell_hours(v),
                                 first=v.day(), last=v.day(), lat=v.lat, lon=v.lon,
                                 category=v.category)
        else:
            st.visits += 1
            st.hours += _dwell_hours(v)
            st.first = min(st.first, v.day())
            st.last = max(st.last, v.day())
            if st.lat is None and v.lat is not None:
                st.lat, st.lon = v.lat, v.lon
            if st.category is None and v.category:
                st.category = v.category
    ranked = sorted(agg.values(), key=lambda s: (s.visits, s.hours), reverse=True)
    return ranked[:limit]


def _safe_day(v: "Visit") -> _dt.date | None:
    try:
        return _dt.date.fromisoformat(v.day())
    except ValueError:
        return None


def movement_stats(*, since_days: int | None = None) -> dict[str, Any]:
    """The shape of your movement: how many places, how many active days, the
    date span, total distance travelled (chronological great-circle between
    consecutive stops), and your busiest day. Honest about coverage — distance
    only counts stops that carry coordinates."""
    visits = sorted(read_all(), key=lambda v: v.start)
    if since_days is not None:
        cutoff = _dt.date.today() - _dt.timedelta(days=max(1, since_days))
        visits = [v for v in visits if _safe_day(v) and _safe_day(v) >= cutoff]
    if not visits:
        return {"visits": 0}
    days = sorted({v.day() for v in visits})
    per_day: dict[str, int] = {}
    for v in visits:
        per_day[v.day()] = per_day.get(v.day(), 0) + 1
    busiest = max(per_day.items(), key=lambda kv: kv[1]) if per_day else (None, 0)
    # total distance: chain great-circle hops between consecutive geo-tagged stops
    dist = 0.0
    prev: tuple[float, float] | None = None
    geo = 0
    for v in visits:
        if v.lat is None or v.lon is None:
            continue
        geo += 1
        if prev is not None:
            dist += haversine_km(prev, (v.lat, v.lon))
        prev = (v.lat, v.lon)
    unique_places = len({(v.place or "").strip().lower() for v in visits})
    span_days = (_dt.date.fromisoformat(days[-1]) - _dt.date.fromisoformat(days[0])).days + 1
    return {
        "visits": len(visits),
        "unique_places": unique_places,
        "active_days": len(days),
        "span_days": span_days,
        "first_day": days[0],
        "last_day": days[-1],
        "distance_km": round(dist, 1),
        "geo_tagged": geo,
        "busiest_day": busiest[0],
        "busiest_day_stops": busiest[1],
    }


def summarize_analysis(*, since_days: int | None = None, top: int = 8) -> str:
    """Human read-out of your movement — the answer to 'which places have I been,
    and what does my movement look like'. Read-only, from the sealed log."""
    if not is_enabled():
        return ("I'm not tracking your places yet — turn it on with "
                "`python3 -m cognitive_twin.places enable` and import a source "
                "(e.g. a Google Timeline/Takeout export).")
    stats = movement_stats(since_days=since_days)
    if not stats.get("visits"):
        window = f"the last {since_days} days" if since_days else "your history"
        return f"No places logged across {window} yet — import a Timeline export first."
    scope = f"last {since_days} days" if since_days else "all time"
    lines = [f"Your movement — {scope}:"]
    lines.append(
        f"  {stats['visits']} stops across {stats['unique_places']} places, "
        f"on {stats['active_days']} day(s) "
        f"({stats['first_day']} → {stats['last_day']})."
    )
    if stats.get("distance_km", 0) > 0.1:
        lines.append(f"  ~{stats['distance_km']:.0f} km travelled between stops "
                     f"({stats['geo_tagged']} geo-tagged).")
    if stats.get("busiest_day"):
        lines.append(f"  Busiest day: {stats['busiest_day']} "
                     f"({stats['busiest_day_stops']} stops).")
    places = top_places(limit=top, since_days=since_days)
    if places:
        lines.append("")
        lines.append("Where you keep going back:")
        for i, p in enumerate(places, 1):
            hrs = f", ~{p.hours:.0f}h total" if p.hours >= 1 else ""
            cat = f" · {p.category}" if p.category else ""
            span = "" if p.first == p.last else f" · {p.first}→{p.last}"
            lines.append(f"  {i}. {p.place} — {p.visits}× visit(s){hrs}{cat}{span}")
    return "\n".join(lines)


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
    if cmd in ("analysis", "analyse", "analyze", "movement", "places"):
        # optional: a trailing number of days to scope the window
        days = None
        if len(argv) > 1 and argv[1].isdigit():
            days = int(argv[1])
        print(summarize_analysis(since_days=days)); return 0
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
          "[today|week|analysis [days]|status|enable|pause|resume|clear]")
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
