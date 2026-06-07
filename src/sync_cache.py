from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


@dataclass
class CacheRecord:
    meta: dict[str, Any]
    items: dict[str, dict[str, Any]]


class SyncCacheManager:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.cache_dir = workspace_root / "memory" / "connectors" / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def load(self, key: str) -> CacheRecord:
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return CacheRecord(meta={}, items={})

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            meta = raw.get("meta", {})
            items = raw.get("items", {})
            if not isinstance(meta, dict):
                meta = {}
            if not isinstance(items, dict):
                items = {}
            return CacheRecord(meta=meta, items=items)
        except Exception:
            return CacheRecord(meta={}, items={})

    def save(self, key: str, record: CacheRecord) -> None:
        path = self.cache_dir / f"{key}.json"
        payload = {"meta": record.meta, "items": record.items}
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def request_with_backoff(method: str, url: str, *, max_attempts: int = 5, timeout: int = 20, **kwargs):
    delay = 0.8
    for attempt in range(1, max_attempts + 1):
        response = requests.request(method, url, timeout=timeout, **kwargs)
        if response.status_code != 429:
            return response

        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                delay = max(delay, float(retry_after))
            except ValueError:
                pass

        if attempt == max_attempts:
            return response

        time.sleep(delay)
        delay = min(delay * 2.0, 12.0)

    return response
