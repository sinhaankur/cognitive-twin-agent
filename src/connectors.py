from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from consent_manager import ConsentManager
from google_oauth import GoogleOAuthManager
from sync_cache import CacheRecord, SyncCacheManager, request_with_backoff


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

    calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "")
    if not calendar_id:
        return _load_fallback_json(workspace_root / "memory" / "connectors" / "calendar.json")

    now = datetime.now(timezone.utc)
    time_min = now.isoformat().replace("+00:00", "Z")
    time_max = (now + timedelta(days=2)).isoformat().replace("+00:00", "Z")

    oauth = GoogleOAuthManager()
    access_token = oauth.get_access_token()
    api_key = os.getenv("GOOGLE_CALENDAR_API_KEY", "")
    if not access_token and not api_key:
        return _load_fallback_json(workspace_root / "memory" / "connectors" / "calendar.json")

    params = {
        "singleEvents": "true",
        "orderBy": "startTime",
        "timeMin": time_min,
        "timeMax": time_max,
        "maxResults": "25",
    }
    headers: dict[str, str] = {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    elif api_key:
        params["key"] = api_key

    url = f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"

    try:
        response = request_with_backoff("GET", url, params=params, headers=headers, timeout=10)
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

    cache = SyncCacheManager(workspace_root)
    record = cache.load("notion_tasks")
    cursor = None
    updated_items: dict[str, dict[str, Any]] = {}

    body: dict[str, Any] = {}
    last_synced = str(record.meta.get("last_synced", ""))
    if last_synced:
        body["filter"] = {
            "timestamp": "last_edited_time",
            "last_edited_time": {"on_or_after": last_synced},
        }

    try:
        while True:
            request_body = dict(body)
            if cursor:
                request_body["start_cursor"] = cursor

            response = request_with_backoff("POST", url, headers=headers, json=request_body, timeout=10)
            response.raise_for_status()
            payload = response.json()

            for row in payload.get("results", []):
                if not isinstance(row, dict):
                    continue

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

                notion_id = str(row.get("id", ""))
                if not notion_id:
                    continue

                updated_items[notion_id] = {
                    "id": notion_id,
                    "title": title,
                    "priority": priority,
                    "status": status,
                    "owner": "self",
                    "source": "notion",
                    "last_edited_time": row.get("last_edited_time", ""),
                }

            if not payload.get("has_more"):
                break
            cursor = payload.get("next_cursor")

    except Exception:
        # Return cached tasks if live sync fails.
        if record.items:
            return list(record.items.values())
        return _load_fallback_json(workspace_root / "memory" / "connectors" / "tasks.json")

    merged = dict(record.items)
    merged.update(updated_items)
    cache.save(
        "notion_tasks",
        CacheRecord(
            meta={"last_synced": datetime.now(timezone.utc).isoformat()},
            items=merged,
        ),
    )
    return list(merged.values())


def fetch_todoist_tasks(workspace_root: Path, consent_manager: ConsentManager) -> list[dict[str, Any]]:
    connector = "todoist"
    if not consent_manager.has_consent(connector):
        return []

    token = os.getenv("TODOIST_API_TOKEN", "")
    if not token:
        return []

    url = "https://api.todoist.com/sync/v9/sync"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/x-www-form-urlencoded"}
    cache = SyncCacheManager(workspace_root)
    record = cache.load("todoist_tasks")
    sync_token = str(record.meta.get("sync_token", "*")) or "*"

    data = {
        "sync_token": sync_token,
        "resource_types": '["items"]',
    }

    try:
        response = request_with_backoff("POST", url, headers=headers, data=data, timeout=10)
        response.raise_for_status()
        payload = response.json()
    except Exception:
        if record.items:
            return list(record.items.values())
        return []

    items_map = dict(record.items)
    priority_map = {1: "low", 2: "medium", 3: "high", 4: "critical"}
    for row in payload.get("items", []):
        if not isinstance(row, dict):
            continue

        task_id = str(row.get("id", ""))
        if not task_id:
            continue

        if bool(row.get("is_deleted", False)):
            items_map.pop(task_id, None)
            continue

        items_map[task_id] = {
            "id": task_id,
            "title": row.get("content", "Untitled task"),
            "priority": priority_map.get(int(row.get("priority", 2)), "medium"),
            "status": "todo" if not row.get("checked", False) else "done",
            "owner": "self",
            "source": "todoist",
        }

    next_sync_token = str(payload.get("sync_token", sync_token))
    cache.save(
        "todoist_tasks",
        CacheRecord(meta={"sync_token": next_sync_token}, items=items_map),
    )
    return list(items_map.values())
