from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from connectors import fetch_google_calendar_events, fetch_notion_tasks, fetch_todoist_tasks
from consent_manager import ConsentManager


@dataclass
class DayMap:
    timestamp: str
    calendar_items: list[dict]
    task_items: list[dict]
    inferred_focus: str


def build_day_map(workspace_root: Path) -> DayMap:
    consent_manager = ConsentManager(workspace_root)

    calendar_items = fetch_google_calendar_events(workspace_root, consent_manager)
    notion_items = fetch_notion_tasks(workspace_root, consent_manager)
    todoist_items = fetch_todoist_tasks(workspace_root, consent_manager)
    task_items = notion_items + todoist_items

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
    import json

    return (
        "# DAILY CONTEXT\n"
        f"timestamp: {day_map.timestamp}\n"
        f"inferred_focus: {day_map.inferred_focus}\n\n"
        "## CALENDAR ITEMS\n"
        f"{json.dumps(day_map.calendar_items, ensure_ascii=True)}\n\n"
        "## TASK ITEMS\n"
        f"{json.dumps(day_map.task_items, ensure_ascii=True)}\n"
    )
