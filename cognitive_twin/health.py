"""
Health & activity — Vera understands how you move, from an Apple Health export.

macOS has no HealthKit (that's iOS only), so the on-device, works-today path is an
Apple Health EXPORT: on the iPhone, Health → your profile → Export All Health Data
→ AirDrop the `export.zip` to the Mac. Vera parses it LOCALLY and keeps only small
aggregates (workout counts, types, active days, steps) — never the raw records,
nothing uploaded. Live HealthKit reads will come with the iPhone companion.

Opt-in like every sense: nothing happens until you point her at an export. The
derived summary feeds her context so she can say 'you've been consistent this
week' or 'looks like a rest day' — grounded, not guessed.
"""

from __future__ import annotations

import datetime as _dt
import os
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

_FILE = "health.json"          # the sealed, derived summary we keep
_FLAG = "health.on"            # opt-in flag


def _home() -> Path:
    from . import security
    return security.home()


def enable(on: bool = True) -> None:
    p = _home() / _FLAG
    if on:
        p.touch()
    elif p.exists():
        p.unlink()


def is_enabled() -> bool:
    return (_home() / _FLAG).exists()


def _save(summary: dict[str, Any]) -> None:
    from . import security
    security.write_state(_home() / _FILE, summary)


def load() -> dict[str, Any]:
    from . import security
    return security.read_state(_home() / _FILE, default={}) or {}


# ── parse an Apple Health export ────────────────────────────────────────────────
def import_export(path: str) -> dict[str, Any]:
    """Parse an Apple Health export (a .zip or the export.xml inside it) and store a
    small summary. Returns the summary (or an {'error': ...}). On-device only."""
    enable(True)
    p = Path(os.path.expanduser(path))
    if not p.exists():
        return {"error": f"no file at {p}"}
    try:
        xml_bytes = _read_export_xml(p)
    except Exception as e:                       # noqa: BLE001
        return {"error": f"couldn't read the export: {e}"}
    if not xml_bytes:
        return {"error": "no export.xml found in that file"}

    workouts: dict[str, int] = {}
    workout_days: set[str] = set()
    step_days: dict[str, float] = {}
    total_workouts = 0
    # stream-parse (these files are big) — count workouts by type + active days,
    # and sum steps per day. Keep nothing else.
    try:
        for _evt, el in ET.iterparse(_bytes_io(xml_bytes), events=("end",)):
            tag = el.tag
            if tag == "Workout":
                wt = (el.get("workoutActivityType") or "")\
                    .replace("HKWorkoutActivityType", "")
                workouts[wt] = workouts.get(wt, 0) + 1
                total_workouts += 1
                d = (el.get("startDate") or "")[:10]
                if d:
                    workout_days.add(d)
                el.clear()
            elif tag == "Record" and el.get("type") == "HKQuantityTypeIdentifierStepCount":
                d = (el.get("startDate") or "")[:10]
                try:
                    step_days[d] = step_days.get(d, 0.0) + float(el.get("value") or 0)
                except ValueError:
                    pass
                el.clear()
    except ET.ParseError as e:
        return {"error": f"malformed export: {e}"}

    # recent window: active days + avg steps over the last 30 days
    cutoff = (_dt.date.today() - _dt.timedelta(days=30)).isoformat()
    recent_workout_days = sorted(d for d in workout_days if d >= cutoff)
    recent_steps = {d: v for d, v in step_days.items() if d >= cutoff}
    avg_steps = round(sum(recent_steps.values()) / len(recent_steps)) if recent_steps else 0

    top = sorted(workouts.items(), key=lambda kv: -kv[1])[:5]
    summary = {
        "imported": _dt.date.today().isoformat(),
        "total_workouts": total_workouts,
        "top_workouts": [{"type": t, "count": c} for t, c in top],
        "active_days_30d": len(recent_workout_days),
        "avg_steps_30d": avg_steps,
        "last_workout": max(workout_days) if workout_days else "",
    }
    _save(summary)
    return summary


def _read_export_xml(p: Path) -> bytes:
    if p.suffix.lower() == ".zip" or zipfile.is_zipfile(p):
        with zipfile.ZipFile(p) as z:
            for name in z.namelist():
                if name.endswith("export.xml"):
                    return z.read(name)
        return b""
    return p.read_bytes()


def _bytes_io(b: bytes):
    import io
    return io.BytesIO(b)


# ── recap for her context ───────────────────────────────────────────────────────
def recap() -> str:
    """A short, human read of your activity — for 'how's my fitness', 'have I been
    working out'. Empty if she hasn't been given an export."""
    if not is_enabled():
        return ""
    s = load()
    if not s or not s.get("total_workouts"):
        return ""
    bits = []
    ad = s.get("active_days_30d", 0)
    if ad:
        tone = ("really consistent" if ad >= 18 else
                "fairly steady" if ad >= 10 else
                "a bit light")
        bits.append(f"you worked out on {ad} of the last 30 days ({tone})")
    top = s.get("top_workouts") or []
    if top:
        bits.append("mostly " + ", ".join(t["type"] for t in top[:3] if t.get("type")))
    if s.get("avg_steps_30d"):
        bits.append(f"~{s['avg_steps_30d']:,} steps a day")
    if s.get("last_workout"):
        bits.append(f"last workout {s['last_workout']}")
    if not bits:
        return ""
    return "Your activity (from an Apple Health export, on-device): " + "; ".join(bits) + "."


def status() -> str:
    if not is_enabled():
        return "health off (point her at an Apple Health export to turn it on)"
    s = load()
    if not s:
        return "health on — no export imported yet"
    return f"health on — {s.get('total_workouts', 0)} workouts known"
