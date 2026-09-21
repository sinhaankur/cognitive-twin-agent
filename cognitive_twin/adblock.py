"""
adblock — Vera's optional control of a self-hosted AdGuard Home ad-blocker.

AdGuard Home (https://github.com/AdguardTeam/AdGuardHome) is an open-source
network-wide DNS ad/tracker blocker. Run as a small Docker container on an
*always-on box you own* (a Raspberry Pi, a NAS, a mini-PC — **not** your daily
laptop), it blocks ads for every device on the home Wi-Fi by answering DNS.

This module lets Vera:
  1. READ  — is protection on? how many queries / how many blocked today? A quick
     "is the house shielded?" read the twin can speak back.
  2. TOGGLE — pause / resume filtering, via AdGuard Home's own HTTP API.
  3. CONTROL THE CONTAINER — start / stop / restart the AdGuard Home Docker
     container **on the remote box**, via that box's Docker API or an
     allow-listed SSH command the user configured.

Posture (identical to watchtower.py / control.py — see SECURITY.md):
  - OFF BY DEFAULT. Nothing here runs until the user opts in
    (env CTWIN_ADBLOCK=1, or adblock.enabled in the agent config).
  - REMOTE, NEVER LOCAL. This controls a box the USER runs the container on. It
    will REFUSE to spin up or bind a DNS container on this machine — binding
    port 53 locally can break the host's own networking. `host` defaults to
    loopback for the *read-only* API; container control requires an explicit,
    non-local box address the user sets. (Ankur's rule: never install the
    ad-blocker on this Mac.)
  - CONFIRM BEFORE MUTATING. Pause/resume filtering and start/stop/restart the
    container go through the same confirmation hook as screen control. Deny =
    nothing runs.
  - NO ARBITRARY SHELL. Container actions are a fixed, named set mapped to exact
    argv (docker start/stop/restart <name>, or an allow-listed SSH invocation) —
    never an interpolated shell string.
  - NO SECRETS LEAVE. Only the AdGuard admin credential (from the Keychain via
    secrets_store) is sent, and only to the box the user named. Never
    conversation, persona, or memory.
  - BEST-EFFORT. A down / unreachable box never breaks the agent loop.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import urllib.request
from typing import Any, Callable

# AdGuard Home's HTTP API. Loopback by default for the READ path; the box that
# actually runs it is set by the user (CTWIN_ADBLOCK_HOST) and is required for
# any container control. Never assume a host — refuse local container ops.
DEFAULT_API = "http://127.0.0.1:3000"
_TIMEOUT = 3.0

_STATUS_PATH = "/control/status"
_STATS_PATH = "/control/stats"
_PROTECT_PATH = "/control/protection"     # POST {"enabled": bool} to pause/resume

# The only container operations we ever run — a closed set, mapped to argv.
_CONTAINER_OPS = ("start", "stop", "restart")

# Hosts we refuse to run *container* control against — protecting this machine.
_LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1", "0.0.0.0"}


# ---- opt-in gate --------------------------------------------------------------
def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in {"1", "true", "yes", "on"}


def is_enabled(cfg: dict | None = None) -> bool:
    block = (cfg or {}).get("adblock") if cfg else None
    if isinstance(block, dict) and "enabled" in block:
        return bool(block["enabled"])
    return _truthy(os.environ.get("CTWIN_ADBLOCK"))


def api_base(cfg: dict | None = None) -> str:
    block = (cfg or {}).get("adblock") if cfg else None
    if isinstance(block, dict) and block.get("api"):
        return str(block["api"]).rstrip("/")
    env = os.environ.get("CTWIN_ADBLOCK_API", "").strip()
    return (env or DEFAULT_API).rstrip("/")


def _box_host(cfg: dict | None = None) -> str:
    """The remote box that runs the container (for container control only)."""
    block = (cfg or {}).get("adblock") if cfg else None
    if isinstance(block, dict) and block.get("host"):
        return str(block["host"]).strip()
    return os.environ.get("CTWIN_ADBLOCK_HOST", "").strip()


def _container_name(cfg: dict | None = None) -> str:
    block = (cfg or {}).get("adblock") if cfg else None
    if isinstance(block, dict) and block.get("container"):
        return str(block["container"]).strip()
    return os.environ.get("CTWIN_ADBLOCK_CONTAINER", "adguardhome").strip()


# ---- confirmation hook (mutating actions) ------------------------------------
ConfirmFn = Callable[[str], bool]
_confirm: ConfirmFn = lambda _action: False   # default: deny (safe)


def set_confirm(fn: ConfirmFn) -> None:
    global _confirm
    _confirm = fn


class AdblockDenied(Exception):
    pass


# ---- auth --------------------------------------------------------------------
def _auth_header() -> dict[str, str]:
    """Basic auth for the AdGuard admin API, pulled from the Keychain (never .env,
    never hard-coded). Returns {} if no credential is stored — read calls that
    don't need auth still work; mutating calls will get a clean 401 we report."""
    try:
        from . import secrets_store
        user = secrets_store.get("adblock_user") or ""
        pw = secrets_store.get("adblock_pass") or ""
    except Exception:
        user, pw = "", ""
    if not (user and pw):
        return {}
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _get(path: str, cfg: dict | None = None) -> dict | None:
    url = api_base(cfg) + path
    try:
        req = urllib.request.Request(url, headers=_auth_header())
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def _post(path: str, body: dict, cfg: dict | None = None) -> bool:
    url = api_base(cfg) + path
    try:
        data = json.dumps(body).encode()
        headers = {"Content-Type": "application/json", **_auth_header()}
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


# ---- READ --------------------------------------------------------------------
def status(cfg: dict | None = None) -> str:
    """A short, speakable read of the shield's state."""
    if not is_enabled(cfg):
        return ("The ad-blocker link is off. Turn it on with `CTWIN_ADBLOCK=1` "
                "once you're running AdGuard Home on your always-on box.")
    st = _get(_STATUS_PATH, cfg)
    if st is None:
        return ("I can't reach AdGuard Home. Is the container up on the box, and "
                f"is the API reachable at {api_base(cfg)}?")
    protected = st.get("protection_enabled", None)
    stats = _get(_STATS_PATH, cfg) or {}
    total = stats.get("num_dns_queries")
    blocked = stats.get("num_blocked_filtering")
    pct = (100 * blocked / total) if (total and blocked is not None) else None
    lead = "Protection is ON." if protected else "Protection is PAUSED." if protected is not None else "AdGuard Home is up."
    if total is not None and blocked is not None:
        tail = f" Today: {blocked:,} of {total:,} queries blocked" + (f" ({pct:.0f}%)." if pct is not None else ".")
    else:
        tail = ""
    return lead + tail


def snapshot(cfg: dict | None = None) -> dict[str, Any]:
    """Structured state for a panel / other code."""
    if not is_enabled(cfg):
        return {"enabled": False}
    st = _get(_STATUS_PATH, cfg) or {}
    stats = _get(_STATS_PATH, cfg) or {}
    return {
        "enabled": True,
        "reachable": bool(st),
        "protection": st.get("protection_enabled"),
        "queries": stats.get("num_dns_queries"),
        "blocked": stats.get("num_blocked_filtering"),
    }


# ---- TOGGLE filtering (via AdGuard API) --------------------------------------
def set_protection(on: bool, cfg: dict | None = None) -> str:
    """Pause / resume filtering. Mutating → goes through the confirmation hook."""
    if not is_enabled(cfg):
        return "The ad-blocker link is off (CTWIN_ADBLOCK=1 to enable)."
    action = f"{'Resume' if on else 'Pause'} ad-blocking on the home network"
    if not _confirm(action):
        return f"Cancelled — did not {action.lower()}."
    ok = _post(_PROTECT_PATH, {"enabled": bool(on)}, cfg)
    return (f"Ad-blocking {'resumed' if on else 'paused'}."
            if ok else "Couldn't reach AdGuard Home to change protection.")


# ---- CONTROL THE CONTAINER (remote box only) ---------------------------------
def container(op: str, cfg: dict | None = None) -> str:
    """start / stop / restart the AdGuard Home container ON THE REMOTE BOX.

    Refuses to run against this machine (protecting the host). Requires an
    explicit non-local box host the user configured. Goes through the confirm
    hook. Uses an allow-listed SSH invocation to the box's docker — never a shell
    string, never the local docker socket.
    """
    if not is_enabled(cfg):
        return "The ad-blocker link is off (CTWIN_ADBLOCK=1 to enable)."
    if op not in _CONTAINER_OPS:
        return f"Unknown op {op!r}. One of: {', '.join(_CONTAINER_OPS)}."

    host = _box_host(cfg)
    if host in _LOCAL_HOSTS:
        return ("Refusing to control a DNS container on THIS machine — that can "
                "break its networking. Set `CTWIN_ADBLOCK_HOST` to your always-on "
                "box (e.g. the Pi's LAN IP) and run it there.")

    name = _container_name(cfg)
    action = f"{op} the '{name}' AdGuard Home container on {host}"
    if not _confirm(action):
        return f"Cancelled — did not {action}."

    # SSH user for the box (config/env); the box must have your key + docker.
    user = (cfg or {}).get("adblock", {}).get("ssh_user") if cfg else None
    user = user or os.environ.get("CTWIN_ADBLOCK_SSH_USER", "").strip()
    target = f"{user}@{host}" if user else host

    # Fixed argv — NO shell interpolation. `docker <op> <name>` on the remote box.
    argv = [
        "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", target,
        "docker", op, name,
    ]
    try:
        res = subprocess.run(argv, capture_output=True, text=True, timeout=20)
    except Exception as e:  # noqa: BLE001 — best-effort, never break the loop
        return f"Couldn't reach {host}: {e}"
    if res.returncode == 0:
        return f"Done — {op}ed AdGuard Home on {host}."
    return f"The box refused: {(res.stderr or res.stdout or 'unknown error').strip()[:200]}"


# ---- the one-time setup command we hand the user (never run here) -------------
def setup_hint() -> str:
    """The exact command to run ON THE ALWAYS-ON BOX (not here). Printed, never
    executed — Vera does not spin up the container; the user owns that box."""
    return (
        "Run this ON YOUR ALWAYS-ON BOX (a Pi / NAS / mini-PC — NOT this laptop):\n\n"
        "  docker run -d --name adguardhome --restart unless-stopped \\\n"
        "    -p 53:53/tcp -p 53:53/udp -p 3000:3000/tcp -p 80:80/tcp \\\n"
        "    -v adguard-work:/opt/adguardhome/work \\\n"
        "    -v adguard-conf:/opt/adguardhome/conf \\\n"
        "    adguard/adguardhome\n\n"
        "Then open http://<box-ip>:3000 to finish setup, and set your ROUTER's\n"
        "DNS to <box-ip> so every device is covered. Point Vera at it with\n"
        "CTWIN_ADBLOCK=1 and CTWIN_ADBLOCK_HOST=<box-ip>."
    )
