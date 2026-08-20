"""
think_routes — Vera's standing, multi-route THINKING loop.

Ankur wants Vera to "keep thinking and working on multiple routes" — plan across
several projects at once, weighted toward UX + visualization (his core), guided
by Lean principles (smallest next step that delivers value; no waste).

Design boundaries (deliberate, matching Vera's security posture):
  • THINK freely, ACT only through the existing sandboxed drive_* tools that the
    user launches. This skill never edits code or runs commands — it produces a
    reviewable PLAN. "User-action-only" holds for every change.
  • GROUNDED, never invented. It reasons ONLY from the real project catalog
    (projects_db) — it must not fabricate facts (no "recent macOS update",
    no imagined bugs). Where it lacks information, it says so and asks.

Output is a single plan file the user reads: ~/.cognitive-twin/routes/plan.md.
One call = one bounded pass over the top-N routes; it is NOT a daemon.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path

from .base import default_registry as R
from . import projects_db

# Ankur's core lens — routes touching these get a small ranking boost so the loop
# spends its budget where he cares most.
_CORE_TAGS = ("ux", "visualization", "viz", "design", "engine", "webgl")

# The prompt fragment that keeps the planner honest + Lean. Handed to the caller
# (the agent) so the model plans under these rules; enforced by grounding the
# context to real project data only.
PLANNER_RULES = (
    "You are Ankur's twin, planning his actual work. Rules:\n"
    "1. GROUND every point in the project facts given below. Never invent status, "
    "bugs, events, or details you were not told — if you don't know, say so and "
    "pose it as a question.\n"
    "2. LEAN: propose the smallest next step that delivers real value; cut waste; "
    "no big-bang rewrites.\n"
    "3. UX + visualization first — that's the core. Favor what improves the user's "
    "understanding and the visual read.\n"
    "4. Be concrete and terse, in Ankur's voice. One clear next action per route."
)


def _dir() -> Path:
    root = Path(os.environ.get("CTWIN_MEMORY_DIR", Path.home() / ".cognitive-twin"))
    d = root / "routes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rank(project: dict) -> tuple[int, str]:
    """Sort key: core-lens projects first (0), then by staleness (oldest update
    first). Returns (bucket, updated) — Python sorts tuples left-to-right."""
    tags = {t.lower() for t in project.get("tags", [])}
    name = project.get("name", "").lower()
    is_core = bool(tags & set(_CORE_TAGS)) or any(k in name for k in ("ux", "engine", "terrain", "universe"))
    return (0 if is_core else 1, project.get("updated", ""))


def _active_routes(limit: int) -> list[dict]:
    """The routes worth thinking about now: active/idea/paused projects, ranked by
    core-lens then staleness, capped to a bounded budget."""
    routes = [
        p for p in projects_db._load().values()
        if p.get("status") in {"idea", "active", "paused"}
    ]
    routes.sort(key=_rank)
    return routes[: max(1, limit)]


@R.add(
    "think_routes",
    "Vera's multi-route thinking pass: read Ankur's real projects and lay out the "
    "next best step for each of the top routes (UX/visualization-weighted, Lean, "
    "grounded only in the catalog — never invented). Writes a reviewable plan the "
    "user reads before any drive. Use when asked to 'keep thinking' / work across "
    "projects. Bounded (one pass), and it never edits code — acting stays with the "
    "sandboxed drive tools the user launches.",
    {"type": "object", "properties": {
        "limit": {"type": "integer", "description": "how many routes to plan (default 4)"}},
    },
)
def think_routes(limit: int = 4) -> str:
    routes = _active_routes(limit)
    if not routes:
        return "No active routes to think about — the project catalog is empty or all shipped/dropped."

    # Build the grounded context block (real facts only) + the planner rules. The
    # agent's model turns this into the actual per-route reasoning; here we lay out
    # the honest source material and a skeleton so nothing is fabricated.
    ts = _dt.datetime.now().isoformat(timespec="minutes")
    ctx = [f"# Routes in play ({len(routes)}) — grounded facts from the catalog"]
    for p in routes:
        ctx.append(f"\n## {p['name']}  ·  {p.get('status', 'idea')}")
        ctx.append(p.get("summary", "").strip() or "(no summary on file)")
        if p.get("next_step"):
            ctx.append(f"- known next step: {p['next_step']}")
        if p.get("open_questions"):
            ctx.append(f"- open question: {p['open_questions']}")
        if p.get("tags"):
            ctx.append(f"- tags: {', '.join(p['tags'])}")

    plan_path = _dir() / "plan.md"
    header = (
        f"# Vera — multi-route plan\n_generated {ts}_\n\n"
        "Thinking pass across the top routes (UX + visualization first, Lean, "
        "grounded in the real catalog). Review, then launch a sandboxed drive on "
        "whichever route you want Vera to act on.\n\n"
        + PLANNER_RULES + "\n\n---\n"
        + "\n".join(ctx) + "\n"
    )
    plan_path.write_text(header, encoding="utf-8")

    names = ", ".join(p["name"] for p in routes)
    return (
        f"Thought across {len(routes)} routes ({names}). Grounded context written to "
        f"{plan_path}. Reason each route's single next step under the planner rules "
        f"(UX/viz-first, Lean, no invented facts), then propose which to drive."
    )
