from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class DayMap:
    timestamp: str
    calendar_items: list[dict]
    task_items: list[dict]
    inferred_focus: str


def load_json_list(path: Path) -> list[dict]:
    if not path.exists() or not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
    except Exception:
        return []
    return []


def build_day_map(workspace_root: Path) -> DayMap:
    calendar_items = load_json_list(workspace_root / "memory" / "connectors" / "calendar.json")
    task_items = load_json_list(workspace_root / "memory" / "connectors" / "tasks.json")

    inferred_focus = "general"
    if any(item.get("priority") == "high" for item in task_items):
        inferred_focus = "high-priority execution"
    elif calendar_items:
        inferred_focus = "schedule-aligned execution"

    return DayMap(
        timestamp=datetime.utcnow().isoformat(),
        calendar_items=calendar_items,
        task_items=task_items,
        inferred_focus=inferred_focus,
    )


def day_map_to_prompt(day_map: DayMap) -> str:
    return (
        "# DAILY CONTEXT\n"
        f"timestamp: {day_map.timestamp}\n"
        f"inferred_focus: {day_map.inferred_focus}\n\n"
        "## CALENDAR ITEMS\n"
        f"{json.dumps(day_map.calendar_items, ensure_ascii=True)}\n\n"
        "## TASK ITEMS\n"
        f"{json.dumps(day_map.task_items, ensure_ascii=True)}\n"
    )
