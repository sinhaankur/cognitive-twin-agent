"""
watchtower — Vera's optional bridge to a self-hosted WatchTower instance.

WatchTower (https://github.com/watchtower-ops/watchtower) is an open-source
operations / ML / AI observability platform ("watch every layer, trust every
release"). This module lets Vera:

  1. EMIT its own agent events to a *local* WatchTower — which model answered,
     which backend (Unhosted cluster vs this machine), latency, whether an
     opt-in action fired, when memory sealed. A private "is my twin healthy?"
     panel.
  2. QUERY WatchTower — a short health read-out the twin can speak back.

Posture (same as places/music):
  - OFF BY DEFAULT. Nothing is emitted until the user turns it on
    (CTWIN_WATCHTOWER=1, or watchtower.enabled in the agent config).
  - LOCAL-ONLY BY DEFAULT. The endpoint defaults to 127.0.0.1; pointing it at a
    non-loopback host is an explicit choice the user makes.
  - BEST-EFFORT. A down or missing WatchTower never breaks the agent loop — every
    call swallows its own errors and returns quietly.
  - NO SECRETS LEAVE. Events carry operational metadata (model id, backend,
    latency, event name) — never conversation content, persona, or memory.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any

# WatchTower's local ingest endpoint. Self-hosted, loopback by default.
# Override with CTWIN_WATCHTOWER_BASE (e.g. a WatchTower on another box you own).
DEFAULT_BASE = "http://127.0.0.1:4318"
_INGEST_PATH = "/v1/events"       # events Vera emits
_HEALTH_PATH = "/v1/health"       # WatchTower's own health read
_TIMEOUT = 2.0                    # never make the twin wait on observability


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in {"1", "true", "yes", "on"}


def _cfg_block(cfg: dict[str, Any] | None) -> dict[str, Any]:
    block = (cfg or {}).get("watchtower")
    return block if isinstance(block, dict) else {}


def is_enabled(cfg: dict[str, Any] | None = None) -> bool:
    """The explicit switch. Emitting anything requires the user to opt in —
    presence of a WatchTower is NOT consent to send it Vera's telemetry."""
    if _truthy(os.environ.get("CTWIN_WATCHTOWER")):
        return True
    return bool(_cfg_block(cfg).get("enabled"))


def base_url(cfg: dict[str, Any] | None = None) -> str:
    env = os.environ.get("CTWIN_WATCHTOWER_BASE", "").strip()
    if env:
        return env.rstrip("/")
    base = _cfg_block(cfg).get("base") or _cfg_block(cfg).get("base_url")
    if isinstance(base, str) and base.strip():
        return base.strip().rstrip("/")
    return DEFAULT_BASE


def _post(url: str, payload: dict[str, Any]) -> bool:
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"content-type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return 200 <= r.status < 300
    except Exception:
        # observability is best-effort; never surface a failure to the loop
        return False


def emit(event: str, cfg: dict[str, Any] | None = None, **fields: Any) -> bool:
    """Send one operational event to WatchTower IF enabled. Returns True if it
    was accepted, False if disabled/unreachable (silently). `fields` should be
    operational metadata only — no conversation text, persona, or memory.

    Example: emit("reply", model="unhosted/qwen2.5:14b", backend="unhosted",
                   latency_ms=812, action_fired=False)
    """
    if not is_enabled(cfg):
        return False
    payload = {
        "source": "vera",
        "event": event,
        "ts": time.time(),
        **fields,
    }
    return _post(base_url(cfg) + _INGEST_PATH, payload)


def health(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read WatchTower's own health. Returns a small dict, always — including a
    friendly 'off'/'unreachable' status rather than raising."""
    if not is_enabled(cfg):
        return {"status": "off", "detail": "WatchTower link is off (opt-in)."}
    url = base_url(cfg) + _HEALTH_PATH
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT) as r:
            if 200 <= r.status < 300:
                body = json.loads(r.read().decode("utf-8") or "{}")
                return {"status": "up", **(body if isinstance(body, dict) else {})}
            return {"status": "error", "detail": f"HTTP {r.status}"}
    except Exception as e:  # noqa: BLE001 - a down WatchTower is a normal state
        return {"status": "unreachable", "detail": str(e), "endpoint": url}


def summarize_health(cfg: dict[str, Any] | None = None) -> str:
    """A one-paragraph human read of the WatchTower link, for the twin to speak."""
    h = health(cfg)
    st = h.get("status")
    if st == "off":
        return ("The WatchTower link is off. Turn it on with `CTWIN_WATCHTOWER=1` "
                "(or watchtower.enabled in the agent config) to let Vera report "
                "its own health to a local WatchTower.")
    if st == "up":
        extra = h.get("detail") or h.get("version") or ""
        return f"WatchTower is up at {base_url(cfg)} — Vera's telemetry has a home. {extra}".strip()
    if st == "unreachable":
        return (f"WatchTower link is on, but nothing is answering at "
                f"{h.get('endpoint', base_url(cfg))}. Start your WatchTower instance, "
                "or point CTWIN_WATCHTOWER_BASE at it.")
    return f"WatchTower status: {st} — {h.get('detail', '')}".strip()
