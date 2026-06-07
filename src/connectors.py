from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from consent_manager import ConsentManager


def _load_fallback_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    try:
        import json

        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [row for row in raw if isinstance(row, dict)]
    except Exception:
        return []
    return []


def fetch_google_calendar_events(workspace_root: Path, consent_manager: ConsentManager) -> list[dict[str, Any]]:
    connector = "google_calendar"
    if not consent_manager.has_consent(connector):
        return _load_fallback_json(workspace_root / "memory" / "connectors" / "calendar.json")

    api_key = os.getenv("GOOGLE_CALENDAR_API_KEY", "")
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "")
    if not api_key or not calendar_id:
        return _load_fallback_json(workspace_root / "memory" / "connectors" / "calendar.json")

    now = datetime.now(timezone.utc)
    time_min = now.isoformat().replace("+00:00", "Z")
    time_max = (now + timedelta(days=2)).isoformat().replace("+00:00", "Z")

    params = {
        "key": api_key,
        "singleEvents": "true",
        "orderBy": "startTime",
        "timeMin": time_min,
        "timeMax": time_max,
        "maxResults": "25",
    }
    url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return _load_fallback_json(workspace_root / "memory" / "connectors" / "calendar.json")

    items = []
    for event in payload.get("items", []):
        start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
        end = event.get("end", {}).get("dateTime") or event.get("end", {}).get("date")
        items.append(
            {
                "title": event.get("summary", "Untitled event"),
                "start": start,
                "end": end,
                "type": "meeting",
                "source": "google_calendar",
            }
        )
    return items


def fetch_notion_tasks(workspace_root: Path, consent_manager: ConsentManager) -> list[dict[str, Any]]:
    connector = "notion"
    if not consent_manager.has_consent(connector):
        return _load_fallback_json(workspace_root / "memory" / "connectors" / "tasks.json")

    token = os.getenv("NOTION_API_TOKEN", "")
    database_id = os.getenv("NOTION_DATABASE_ID", "")
    if not token or not database_id:
        return _load_fallback_json(workspace_root / "memory" / "connectors" / "tasks.json")

    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, headers=headers, json={}, timeout=10)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return _load_fallback_json(workspace_root / "memory" / "connectors" / "tasks.json")

    items = []
    for row in payload.get("results", []):
        props = row.get("properties", {})
        title = "Untitled"
        for prop in props.values():
            if prop.get("type") == "title":
                fragments = prop.get("title", [])
                title = "".join(fragment.get("plain_text", "") for fragment in fragments).strip() or "Untitled"
                break

        status = "todo"
        priority = "medium"
        for key, prop in props.items():
            if key.lower() == "status" and prop.get("type") == "status":
                status = (prop.get("status") or {}).get("name", "todo").lower()
            if key.lower() == "priority" and prop.get("type") == "select":
                priority = ((prop.get("select") or {}).get("name", "medium")).lower()

        items.append(
            {
                "title": title,
                "priority": priority,
                "status": status,
                "owner": "self",
                "source": "notion",
            }
        )
    return items


def fetch_todoist_tasks(workspace_root: Path, consent_manager: ConsentManager) -> list[dict[str, Any]]:
    connector = "todoist"
    if not consent_manager.has_consent(connector):
        return []

    token = os.getenv("TODOIST_API_TOKEN", "")
    if not token:
        return []

    url = "https://api.todoist.com/rest/v2/tasks"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []

    items = []
    priority_map = {1: "low", 2: "medium", 3: "high", 4: "critical"}
    for row in payload:
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "title": row.get("content", "Untitled task"),
                "priority": priority_map.get(int(row.get("priority", 2)), "medium"),
                "status": "todo",
                "owner": "self",
                "source": "todoist",
            }
        )
    return items
