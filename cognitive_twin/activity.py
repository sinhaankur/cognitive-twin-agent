"""
Activity awareness — Anita learns how you actually work, by gently noticing what
you're doing on this device over time. All on-device, opt-in, and pausable.

What it records (only when ENABLED and NOT paused): periodic samples of the
frontmost app + (optionally) the active window title, timestamped. From that it
derives patterns — which apps you live in, at which times, what you tend to work
on — and folds a short, private summary into how the twin understands you.

Privacy is first-class:
  - OFF by default. You opt in (enable()).
  - PRIVATE / SNOOZE mode hard-stops all observation — nothing is read or stored
    while it's on (pause() / snooze(minutes)).
  - Everything stays in ~/.cognitive-twin/activity.jsonl, owner-only. Never
    uploaded. You can clear it any time.

This module is pure logic + a tiny osascript probe (macOS); the host (app)
samples on a timer.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import stat
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def _dir() -> Path:
    root = Path(os.environ.get("CTWIN_MEMORY_DIR", Path.home() / ".cognitive-twin"))
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, stat.S_IRWXU)
    except OSError:
        pass
    return root


LOG = "activity.jsonl"
STATE = "activity_state.json"


# --- enable / privacy gate ----------------------------------------------------
def _state() -> dict[str, Any]:
    p = _dir() / STATE
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(s: dict[str, Any]) -> None:
    p = _dir() / STATE
    existed = p.exists()
    try:
        p.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        if not existed:
            os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def is_enabled() -> bool:
    return bool(_state().get("enabled", False))


def enable(on: bool = True) -> None:
    s = _state(); s["enabled"] = on; _save_state(s)


def pause(on: bool = True) -> None:
    """Private mode: when on, nothing is observed or stored, indefinitely."""
    s = _state(); s["paused"] = on; s.pop("snooze_until", None); _save_state(s)


def snooze(minutes: int = 30) -> None:
    """Snooze observation for a while (private window), then auto-resume."""
    until = (_dt.datetime.now() + _dt.timedelta(minutes=minutes)).isoformat()
    s = _state(); s["snooze_until"] = until; s["paused"] = False; _save_state(s)


def is_private() -> bool:
    """True if observation is currently suppressed (paused or within a snooze)."""
    s = _state()
    if s.get("paused"):
        return True
    until = s.get("snooze_until")
    if until:
        try:
            return _dt.datetime.now() < _dt.datetime.fromisoformat(until)
        except ValueError:
            return False
    return False


def observing() -> bool:
    """The single gate: only observe when enabled AND not private."""
    return is_enabled() and not is_private()


# --- the probe (macOS) --------------------------------------------------------
def _frontmost() -> tuple[str, str]:
    """(app name, window title) of the frontmost app. Best-effort; ('','') on
    failure or non-macOS. Window title needs Accessibility permission."""
    if sys.platform != "darwin":
        return ("", "")
    script = (
        'tell application "System Events"\n'
        '  set p to first application process whose frontmost is true\n'
        '  set appName to name of p\n'
        '  set winTitle to ""\n'
        '  try\n'
        '    set winTitle to name of front window of p\n'
        '  end try\n'
        '  return appName & "||" & winTitle\n'
        'end tell'
    )
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True,
                           text=True, timeout=5)
        if r.returncode == 0:
            app, _, title = r.stdout.strip().partition("||")
            return (app.strip(), title.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return ("", "")


def sample(record_titles: bool = True) -> dict[str, Any] | None:
    """Take one activity sample IF we're allowed to. Returns the entry, or None
    when observation is off/private (the privacy gate)."""
    if not observing():
        return None
    app, title = _frontmost()
    if not app:
        return None
    entry: dict[str, Any] = {
        "ts": _dt.datetime.now().isoformat(timespec="seconds"),
        "app": app,
    }
    if record_titles and title:
        entry["title"] = title[:160]
    _append(entry)
    return entry


def _append(entry: dict[str, Any]) -> None:
    p = _dir() / LOG
    existed = p.exists()
    try:
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if not existed:
            os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass


# --- patterns (how you work) --------------------------------------------------
def _entries() -> list[dict[str, Any]]:
    p = _dir() / LOG
    if not p.is_file():
        return []
    out = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


def patterns() -> dict[str, Any]:
    es = _entries()
    if not es:
        return {"samples": 0, "top_apps": [], "by_part_of_day": {}}
    apps: Counter[str] = Counter()
    by_part: dict[str, Counter] = {}
    for e in es:
        app = e.get("app", "")
        if app:
            apps[app] += 1
        try:
            h = _dt.datetime.fromisoformat(e.get("ts", "")).hour
        except ValueError:
            continue
        part = ("morning" if h < 12 else "afternoon" if h < 18 else "evening")
        by_part.setdefault(part, Counter())[app] += 1
    return {
        "samples": len(es),
        "top_apps": [a for a, _ in apps.most_common(6)],
        "by_part_of_day": {k: [a for a, _ in v.most_common(3)] for k, v in by_part.items()},
    }


def summary_for_prompt() -> str:
    """A short, private line about how the user works, for the system prompt."""
    if not is_enabled():
        return ""
    p = patterns()
    if not p["samples"]:
        return ""
    bits = []
    if p["top_apps"]:
        bits.append("apps they live in: " + ", ".join(p["top_apps"]))
    parts = p["by_part_of_day"]
    if parts:
        seg = "; ".join(f"{k}: {', '.join(v)}" for k, v in parts.items() if v)
        if seg:
            bits.append("by time of day — " + seg)
    if not bits:
        return ""
    return ("# HOW YOU WORK (private, on-device, from device activity)\n"
            + " ".join(bits) + ".")


def clear() -> bool:
    p = _dir() / LOG
    try:
        if p.is_file():
            p.unlink(); return True
    except OSError:
        pass
    return False


def status() -> str:
    if not is_enabled():
        return "activity: OFF (opt-in). Anita isn't observing your device."
    if is_private():
        return "activity: PRIVATE — observation paused; nothing is being read."
    n = patterns()["samples"]
    return f"activity: on, {n} samples — private, on-device. Snooze/Private to pause."


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "status"
    if arg == "on":
        enable(True); print("activity learning ON")
    elif arg == "off":
        enable(False); print("activity learning OFF")
    elif arg == "private":
        pause(True); print("PRIVATE mode on — nothing observed")
    elif arg == "resume":
        pause(False); print("resumed")
    elif arg == "sample":
        print(sample() or "(not observing — off or private)")
    elif arg == "clear":
        print("cleared" if clear() else "nothing to clear")
    else:
        print(status())
        if patterns()["samples"]:
            print(summary_for_prompt())
