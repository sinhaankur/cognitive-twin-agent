"""
projects_db — Vera's living catalog of Ankur's projects and ideas.

This is NOT a passive filing cabinet. Vera's purpose is to LEARN, TEACH, and
QUESTION as a cognitive twin — so each entry carries not just what a project IS,
but what's UNRESOLVED about it: open questions, the next decision, what Vera
should follow up on. Vera uses `projects_needing_attention` to surface those and
actually ask Ankur — turning a static list into an ongoing conversation.

Store: ~/.cognitive-twin/projects.jsonl (one JSON object per line; latest entry
per `id` wins, so updates are append-only + recoverable). Sits beside Vera's
memory.jsonl and uses the same CTWIN_MEMORY_DIR root.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any

from .base import default_registry as R


def _dir() -> Path:
    root = Path(os.environ.get("CTWIN_MEMORY_DIR", Path.home() / ".cognitive-twin"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _file() -> Path:
    return _dir() / "projects.jsonl"


def _load() -> dict[str, dict[str, Any]]:
    """Return {id: latest-entry}. Append-only file → last write per id wins."""
    out: dict[str, dict[str, Any]] = {}
    f = _file()
    if not f.exists():
        return out
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
            out[e["id"]] = e
        except (json.JSONDecodeError, KeyError):
            continue
    return out


def _append(entry: dict[str, Any]) -> None:
    with _file().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")[:48]


@R.add(
    "remember_project",
    "Record or update one of Ankur's projects/ideas in Vera's catalog. Capture what "
    "it IS and — importantly — what's UNRESOLVED (open_questions, next_step) so Vera "
    "can follow up later. Updating an existing id merges new fields.",
    {"type": "object", "properties": {
        "name": {"type": "string", "description": "project/idea name"},
        "summary": {"type": "string", "description": "one or two sentences: what it is"},
        "status": {"type": "string", "description": "idea | active | paused | shipped | dropped"},
        "next_step": {"type": "string", "description": "the single next concrete action (optional)"},
        "open_questions": {"type": "string", "description": "what's undecided / what Vera should ask about (optional)"},
        "tags": {"type": "string", "description": "comma-separated tags (optional)"}},
     "required": ["name", "summary"]},
)
def remember_project(name: str, summary: str, status: str = "idea",
                     next_step: str = "", open_questions: str = "", tags: str = "") -> str:
    pid = _slug(name)
    existing = _load().get(pid, {})
    entry = {
        **existing,
        "id": pid,
        "name": name,
        "summary": summary,
        "status": status or existing.get("status", "idea"),
        "next_step": next_step or existing.get("next_step", ""),
        "open_questions": open_questions or existing.get("open_questions", ""),
        "tags": [t.strip() for t in tags.split(",") if t.strip()] or existing.get("tags", []),
        "updated": _dt.datetime.now().isoformat(timespec="seconds"),
        "created": existing.get("created", _dt.datetime.now().isoformat(timespec="seconds")),
    }
    _append(entry)
    verb = "Updated" if existing else "Recorded"
    n = len(_load())
    return f"{verb} project '{name}' ({entry['status']}). Vera is tracking {n} project{'s' if n != 1 else ''}."


@R.add(
    "list_projects",
    "List Ankur's projects/ideas Vera is tracking, optionally filtered by status "
    "(idea/active/paused/shipped/dropped) or a tag.",
    {"type": "object", "properties": {
        "status": {"type": "string", "description": "filter by status (optional)"},
        "tag": {"type": "string", "description": "filter by tag (optional)"}},
    },
)
def list_projects(status: str = "", tag: str = "") -> str:
    items = list(_load().values())
    if status:
        items = [p for p in items if p.get("status") == status]
    if tag:
        items = [p for p in items if tag in p.get("tags", [])]
    if not items:
        return "No matching projects in Vera's catalog yet."
    items.sort(key=lambda p: p.get("updated", ""), reverse=True)
    lines = [f"Vera is tracking {len(items)} project(s):"]
    for p in items:
        line = f"  • {p['name']} [{p.get('status','idea')}] — {p.get('summary','')}"
        if p.get("next_step"):
            line += f"\n      next: {p['next_step']}"
        lines.append(line)
    return "\n".join(lines)


@R.add(
    "search_projects",
    "Search Ankur's project/idea catalog by keyword (matches name, summary, tags, "
    "open questions).",
    {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
)
def search_projects(query: str) -> str:
    q = query.lower()
    hits = []
    for p in _load().values():
        hay = " ".join([
            p.get("name", ""), p.get("summary", ""), p.get("open_questions", ""),
            " ".join(p.get("tags", [])),
        ]).lower()
        if q in hay:
            hits.append(p)
    if not hits:
        return f"No projects match '{query}'."
    hits.sort(key=lambda p: p.get("updated", ""), reverse=True)
    return "\n".join(f"  • {p['name']} [{p.get('status','idea')}] — {p.get('summary','')}" for p in hits)


@R.add(
    "projects_needing_attention",
    "Surface projects with an open question or a defined next step — the ones Vera "
    "should ASK Ankur about. This is how the catalog stays a conversation, not a "
    "static list. Vera should read these and question/nudge accordingly.",
)
def projects_needing_attention() -> str:
    items = [p for p in _load().values()
             if p.get("status") in {"idea", "active", "paused"}
             and (p.get("open_questions") or p.get("next_step"))]
    if not items:
        return "Nothing pending — every active project's next step is clear."
    items.sort(key=lambda p: p.get("updated", ""))  # stalest first
    lines = ["Projects Vera should follow up on:"]
    for p in items:
        lines.append(f"  • {p['name']} [{p.get('status')}]")
        if p.get("open_questions"):
            lines.append(f"      open question: {p['open_questions']}")
        if p.get("next_step"):
            lines.append(f"      next step: {p['next_step']}")
    return "\n".join(lines)
