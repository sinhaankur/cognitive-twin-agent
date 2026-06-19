"""
Built-in MVP skills — safe, local, useful. Importing this module registers them
on the default registry. All file access is sandboxed to a working directory so
the agent can't wander the filesystem.
"""

from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path

from .base import default_registry as R

# Sandbox root for file skills — defaults to ~/.cognitive-twin/workspace, override
# with CTWIN_WORKSPACE. Created on first use.
def _workspace() -> Path:
    root = Path(os.environ.get("CTWIN_WORKSPACE", Path.home() / ".cognitive-twin" / "workspace"))
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()

def _safe_path(rel: str) -> Path:
    """Resolve rel inside the workspace; reject escapes (../, absolute)."""
    root = _workspace()
    p = (root / rel).resolve()
    if root not in p.parents and p != root:
        raise ValueError(f"path '{rel}' is outside the workspace sandbox")
    return p


@R.add("now", "Get the current date and time (local).")
def now() -> str:
    n = _dt.datetime.now()
    return n.strftime("%A, %B %d, %Y · %H:%M")


@R.add(
    "list_dir",
    "List files in a folder inside the workspace.",
    {"type": "object", "properties": {"path": {"type": "string", "description": "folder relative to the workspace; '' for root"}}},
)
def list_dir(path: str = "") -> str:
    p = _safe_path(path or ".")
    if not p.exists():
        return f"[empty] '{path or '.'}' does not exist in the workspace"
    items = sorted(os.listdir(p))
    return "\n".join(items) if items else "[empty]"


@R.add(
    "read_file",
    "Read a UTF-8 text file from the workspace (first ~8 KB).",
    {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
)
def read_file(path: str) -> str:
    p = _safe_path(path)
    if not p.is_file():
        return f"[not found] '{path}'"
    text = p.read_text(encoding="utf-8", errors="replace")
    return text[:8000] + ("\n…[truncated]" if len(text) > 8000 else "")


@R.add(
    "daily_digest",
    "Build a digest of today from LOCAL signals: today's date plus the user's "
    "tasks/notes file in the workspace (tasks.md by default) and an optional .ics "
    "calendar. Use this to summarize the user's day.",
    {"type": "object", "properties": {
        "tasks_file": {"type": "string", "description": "tasks/notes filename in workspace (default tasks.md)"},
        "calendar_file": {"type": "string", "description": "optional .ics filename in workspace"},
    }},
)
def daily_digest(tasks_file: str = "tasks.md", calendar_file: str = "") -> str:
    today = _dt.date.today()
    out: list[str] = [f"Date: {today.strftime('%A, %B %d, %Y')}"]

    # tasks/notes
    try:
        tp = _safe_path(tasks_file)
        if tp.is_file():
            lines = [ln.strip() for ln in tp.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
            out.append(f"\nTasks/notes ({tasks_file}) — {len(lines)} item(s):")
            out.extend(f"  • {ln.lstrip('-* ').strip()}" for ln in lines[:20])
        else:
            out.append(f"\nNo tasks file at '{tasks_file}' in the workspace — add one to enrich the digest.")
    except ValueError as e:
        out.append(f"\n[skip tasks] {e}")

    # very light .ics parse — today's VEVENT SUMMARY lines (no external deps)
    if calendar_file:
        try:
            cp = _safe_path(calendar_file)
            if cp.is_file():
                events = _today_events(cp.read_text(encoding="utf-8", errors="replace"), today)
                out.append(f"\nToday's calendar ({calendar_file}) — {len(events)} event(s):")
                out.extend(f"  • {e}" for e in events[:20])
            else:
                out.append(f"\nNo calendar at '{calendar_file}'.")
        except ValueError as e:
            out.append(f"\n[skip calendar] {e}")

    return "\n".join(out)


def _today_events(ics: str, today: _dt.date) -> list[str]:
    """Minimal .ics: collect SUMMARY of VEVENTs whose DTSTART is today."""
    events: list[str] = []
    cur: dict[str, str] = {}
    in_event = False
    stamp = today.strftime("%Y%m%d")
    for raw in ics.splitlines():
        line = raw.strip()
        if line == "BEGIN:VEVENT":
            in_event, cur = True, {}
        elif line == "END:VEVENT":
            if in_event and cur.get("start", "").startswith(stamp):
                events.append(cur.get("summary", "(untitled)"))
            in_event = False
        elif in_event:
            if line.startswith("DTSTART"):
                cur["start"] = line.split(":", 1)[-1]
            elif line.startswith("SUMMARY"):
                cur["summary"] = line.split(":", 1)[-1]
    return events
