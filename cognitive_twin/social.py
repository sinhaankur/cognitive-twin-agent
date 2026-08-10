"""
social — your Facebook / Instagram life, from YOUR export, sealed on this Mac.

Meta shut down the APIs that would let an app read your feed, and scraping gets
you banned — so the private, honest way to give Vera your social life is Meta's
official **"Download Your Information"** export. You request the zip once, Vera
parses it locally into a sealed index, and reasons over it on-device. Nothing is
scraped; nothing is uploaded.

What Vera tracks from it (all on-device):
  • activity over time  — how much you post/comment/react, per platform, trending.
  • sentiment           — on-device sentiment on the words YOU wrote (a mood trend
                          from your own posts/comments; labelled inference, not fact).
  • who you interact with — the people/pages you engage with most.
  • usage patterns      — when you're active (late-night, etc.), to connect with
                          your rhythms/mood picture.

Privacy — same kernel as everything else:
  • Every activity item is a line SEALED via ``security.append_line`` (ChaCha20,
    device-bound key). The index reads as noise off this Mac.
  • Opt-in + pausable, mirroring ``places`` / ``activity``.
  • It stays in ``~/.cognitive-twin/social.jsonl``, owner-only, never uploaded.

CLI:
    python3 -m cognitive_twin.social summary [--days 90]
    python3 -m cognitive_twin.social status
    python3 -m cognitive_twin.social enable | pause | resume | clear

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import datetime as _dt
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import security


# ── storage + gates (mirror places.py) ─────────────────────────────────────────
def _home() -> Path:
    return security.home()


def _log_path() -> Path:
    return security.path("social.jsonl")


def _flag(name: str) -> Path:
    return _home() / f"social.{name}"


def enable() -> None:
    _flag("enabled").write_text("1", encoding="utf-8")


def disable() -> None:
    _flag("enabled").unlink(missing_ok=True)


def is_enabled() -> bool:
    return _flag("enabled").is_file()


def pause() -> None:
    _flag("paused").write_text("1", encoding="utf-8")


def resume() -> None:
    _flag("paused").unlink(missing_ok=True)


def is_paused() -> bool:
    return _flag("paused").is_file()


def _intake_allowed() -> bool:
    return is_enabled() and not is_paused()


# ── the one record every social source produces ───────────────────────────────
@dataclass
class Activity:
    """One thing you did on a platform: a post, comment, reaction, message."""
    platform: str                 # "facebook" | "instagram"
    kind: str                     # "post" | "comment" | "reaction" | "message" | "like"
    ts: float                     # epoch seconds
    text: str = ""                # your words, if any (for sentiment)
    target: str = ""              # who/what: page/person/thread name
    sentiment: float | None = None  # -1..1, filled on-device at import time
    meta: dict[str, Any] = field(default_factory=dict)

    def day(self) -> str:
        return _dt.datetime.fromtimestamp(self.ts, _dt.timezone.utc).date().isoformat()

    def hour(self) -> int:
        return _dt.datetime.fromtimestamp(self.ts, _dt.timezone.utc).hour


# ── append + read (sealed via kernel) ──────────────────────────────────────────
def import_activities(items: Iterable[Activity], *, dedupe: bool = True) -> int:
    if not _intake_allowed():
        return 0
    existing = {(a.platform, a.kind, a.ts, a.text[:40]) for a in read_all()} if dedupe else set()
    n = 0
    for a in items:
        key = (a.platform, a.kind, a.ts, a.text[:40])
        if dedupe and key in existing:
            continue
        security.append_line(_log_path(), asdict(a))
        existing.add(key)
        n += 1
    return n


def read_all() -> list[Activity]:
    out: list[Activity] = []
    for data in security.read_lines(_log_path()):
        try:
            out.append(Activity(**data))
        except Exception:
            continue
    return out


def clear() -> None:
    _log_path().unlink(missing_ok=True)


# ── the four signals ───────────────────────────────────────────────────────────
def _within(items: list[Activity], days: int) -> list[Activity]:
    if not days:
        return items
    cutoff = _dt.datetime.now(_dt.timezone.utc).timestamp() - days * 86400
    return [a for a in items if a.ts >= cutoff]


def activity_over_time(days: int = 90) -> dict[str, Any]:
    items = _within(read_all(), days)
    by_platform: Counter[str] = Counter(a.platform for a in items)
    by_kind: Counter[str] = Counter(a.kind for a in items)
    # weekly trend of total activity
    weekly: dict[str, int] = defaultdict(int)
    for a in items:
        wk = _dt.datetime.fromtimestamp(a.ts, _dt.timezone.utc).strftime("%Y-W%W")
        weekly[wk] += 1
    return {"total": len(items), "by_platform": dict(by_platform),
            "by_kind": dict(by_kind), "weekly": dict(sorted(weekly.items()))}


def sentiment_trend(days: int = 90) -> dict[str, Any]:
    items = [a for a in _within(read_all(), days) if a.sentiment is not None and a.text]
    if not items:
        return {"count": 0, "avg": None, "monthly": {}}
    monthly: dict[str, list[float]] = defaultdict(list)
    for a in items:
        mo = _dt.datetime.fromtimestamp(a.ts, _dt.timezone.utc).strftime("%Y-%m")
        monthly[mo].append(a.sentiment)
    avg = sum(a.sentiment for a in items) / len(items)
    return {"count": len(items), "avg": round(avg, 3),
            "monthly": {k: round(sum(v) / len(v), 3) for k, v in sorted(monthly.items())}}


def top_interactions(days: int = 90, limit: int = 10) -> list[tuple[str, int]]:
    items = _within(read_all(), days)
    c: Counter[str] = Counter(a.target for a in items if a.target)
    return c.most_common(limit)


def usage_hours(days: int = 90) -> dict[int, int]:
    items = _within(read_all(), days)
    hours: Counter[int] = Counter(a.hour() for a in items)
    return dict(sorted(hours.items()))


# ── human summary ───────────────────────────────────────────────────────────────
def summary(days: int = 90) -> str:
    if not is_enabled():
        return ("Social tracking is off. Turn it on (`social enable`) and import a "
                "Meta export (`importers.meta_export <folder>`).")
    if not read_all():
        return ("No social data yet. Request Meta's 'Download Your Information' "
                "export, then: python3 -m cognitive_twin.importers.meta_export <folder>")
    a = activity_over_time(days)
    s = sentiment_trend(days)
    top = top_interactions(days, 5)
    hrs = usage_hours(days)
    peak = max(hrs, key=hrs.get) if hrs else None

    lines = [f"Your social activity (last {days}d):",
             f"  {a['total']} actions — " + ", ".join(f"{k}: {v}" for k, v in a['by_platform'].items())]
    if a["by_kind"]:
        lines.append("  by type: " + ", ".join(f"{k} {v}" for k, v in a["by_kind"].items()))
    if s["avg"] is not None:
        mood = "positive" if s["avg"] > 0.1 else "negative" if s["avg"] < -0.1 else "neutral"
        lines.append(f"  tone of what you wrote: {mood} (avg {s['avg']:+.2f}, from "
                     f"{s['count']} posts/comments — inference, not fact)")
    if top:
        lines.append("  you engage most with: " + ", ".join(f"{t} ({n})" for t, n in top))
    if peak is not None:
        lines.append(f"  most active around {peak:02d}:00 UTC")
    return "\n".join(lines)


def status() -> str:
    n = len(read_all())
    state = "on" if is_enabled() else "off"
    if is_paused():
        state += " (paused)"
    return f"Social: {state}. {n} activity item(s) sealed on this Mac. Log: {_log_path()}"


# ── CLI ─────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    args = argv[1:]
    days = int(args[args.index("--days") + 1]) if "--days" in args else 90
    if cmd == "enable":
        enable(); print("✓ Social tracking on (opt-in). Import a Meta export next."); return 0
    if cmd == "disable":
        disable(); print("✓ Social tracking off."); return 0
    if cmd == "pause":
        pause(); print("⏸ Paused."); return 0
    if cmd == "resume":
        resume(); print("▶ Resumed."); return 0
    if cmd == "clear":
        clear(); print("✓ Cleared the local social index."); return 0
    if cmd == "status":
        print(status()); return 0
    if cmd == "summary":
        print(summary(days)); return 0
    print("usage: python3 -m cognitive_twin.social [summary|status|enable|pause|resume|clear]")
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
