"""
Privacy mode — the one switch that decides WHO can reach Vera, explained plainly.

Ankur: *"this can be a switch like Tailscale"* — and then: *"privacy mode on this
needs to be understood"* + *"security too"*. The whole point of a reach switch is
that the user UNDERSTANDS exactly what each position exposes. Tailscale is honest
about who's on your tailnet; this is honest about who can talk to Vera.

Three understood states (mutually exclusive):

  🔒 PRIVATE   (default) — Vera binds 127.0.0.1 only. Reachable from THIS Mac and
                nothing else. No other device, no one on your network, can reach
                her. This is the safe default; you have to opt out of it.

  📱 MY_DEVICES          — Vera binds the tailnet (0.0.0.0, reached over Tailscale,
                which you already run). Your phone / other Macs can reach her —
                but ONLY with a device token (a shared secret this file mints), so
                it is NOT "whoever can reach the port". Same reach as Tailscale:
                your devices, no one else's.

  🚫 LOCKDOWN            — the existing global kill switch (security.lockdown).
                Vera stays on-device AND can't reach out / act / send. Independent
                of reach: you can be PRIVATE and locked, or on MY_DEVICES and
                locked. Lockdown always wins.

Why a token matters (the security the user asked about): the HTTP server has no
password and assumes loopback. The moment reach widens to the tailnet, "anyone who
can reach the port" could talk to Vera. The device token closes that: tailnet
requests must carry it; loopback (this Mac) never needs it. So widening reach does
NOT widen trust — only devices you've paired get in.

Nothing here uploads anything; Tailscale is a private mesh of machines YOU own.
"""

from __future__ import annotations

import os
import secrets
from typing import Any

from . import security

# Reach states.
PRIVATE = "private"        # 127.0.0.1 — this Mac only (default)
MY_DEVICES = "my_devices"  # tailnet, token-gated — your devices only

_STATE_FILE = "privacy.json"
_TOKEN_FILE = "device_token"  # owner-only; the shared secret paired devices carry

# Safe Mode is ON by default — the user is in control "for sure". Vera can think,
# chat, and READ (code/memory RAG), but every OUTWARD or MUTATING action is blocked
# until the user authorizes THAT task. A granted task is allowed once, then re-locks
# (Ankur: "unless certain tasks are planned or asked for").
_SAFE_DEFAULT = True


def _state() -> dict[str, Any]:
    return security.read_state(security.path(_STATE_FILE), default={}) or {}


def reach() -> str:
    """Current reach state. An explicit env override wins (so a launcher can pin
    it); otherwise the saved choice; otherwise PRIVATE — the safe default."""
    env = os.environ.get("VERA_REACH", "").strip().lower()
    if env in {PRIVATE, MY_DEVICES}:
        return env
    val = _state().get("reach")
    return val if val in {PRIVATE, MY_DEVICES} else PRIVATE


def set_reach(state: str) -> dict[str, Any]:
    """Set the reach state. Minting the device token on first widen so MY_DEVICES
    is never open. Records the change in the sealed audit (who/when)."""
    if state not in {PRIVATE, MY_DEVICES}:
        raise ValueError(f"unknown reach state: {state!r}")
    if state == MY_DEVICES:
        ensure_token()  # never widen reach without a token in place
    data = _state()
    data["reach"] = state
    security.write_state(security.path(_STATE_FILE), data)
    try:
        security.append_line(security.path("audit.log"),
                             {"event": "privacy.reach", "state": state})
    except Exception:
        pass
    return status()


def bind_host() -> str:
    """The address the server should bind, derived from the reach state. PRIVATE →
    loopback; MY_DEVICES → all interfaces (Tailscale carries it to your devices).
    This is what the server/launcher reads instead of hard-coding VERA_HOST."""
    # An explicit VERA_HOST still wins (power users / tests), else derive from reach.
    forced = os.environ.get("VERA_HOST", "").strip()
    if forced:
        return forced
    return "0.0.0.0" if reach() == MY_DEVICES else "127.0.0.1"


# ── device token: makes MY_DEVICES "your devices" not "anyone on the port" ──────
def ensure_token() -> str:
    """Return the device token, minting a fresh owner-only one if absent. Paired
    devices send it; loopback requests are exempt (same Mac = already trusted)."""
    p = security.path(_TOKEN_FILE)
    if p.is_file():
        tok = p.read_text(encoding="utf-8").strip()
        if tok:
            return tok
    tok = secrets.token_urlsafe(24)
    p.write_text(tok, encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return tok


def token() -> str | None:
    """The current device token, or None if MY_DEVICES was never enabled."""
    p = security.path(_TOKEN_FILE)
    if p.is_file():
        tok = p.read_text(encoding="utf-8").strip()
        return tok or None
    return None


def rotate_token() -> str:
    """Mint a NEW token (un-pairs every device until they get the new one). Use if
    you think the old one leaked — the security equivalent of Tailscale re-auth."""
    security.path(_TOKEN_FILE).unlink(missing_ok=True)
    return ensure_token()


def request_allowed(remote_ip: str, header_token: str | None) -> bool:
    """Gate a single HTTP request. Loopback (this Mac) is always allowed — same
    trust as today. Off-box requests are allowed ONLY when reach is MY_DEVICES AND
    the request carries the device token. Anything else is refused. Fail-closed."""
    ip = (remote_ip or "").strip()
    if ip in {"127.0.0.1", "::1", "localhost"}:
        return True
    if reach() != MY_DEVICES:
        return False  # not sharing beyond this Mac
    tok = token()
    return bool(tok) and header_token == tok


# ── SAFE MODE: read freely, act only when you authorize the task ────────────────
#
# This is the heart of "the user is in control for sure". When Safe Mode is ON
# (the default), Vera may think/chat/READ, but any outward or mutating capability
# (send email, control the Mac, run an action, push) must be AUTHORIZED first —
# per task, not forever. Granting a task opens a short window for that one kind of
# action, then it re-locks. Independent of the Kill Switch: lockdown halts
# EVERYTHING; Safe Mode is the everyday, finer-grained "ask before you act".

# Actions that are always fine even in Safe Mode (no side effects off the surface).
_READONLY = frozenset({"think", "chat", "answer", "read", "retrieve", "recall",
                       "search", "view", "status", "diagnose"})


def safe_mode() -> bool:
    """True when Safe Mode is engaged. Env override wins; else saved; else default."""
    env = os.environ.get("VERA_SAFE_MODE", "").strip().lower()
    if env in {"1", "true", "on", "yes"}:
        return True
    if env in {"0", "false", "off", "no"}:
        return False
    val = _state().get("safe_mode")
    return bool(val) if isinstance(val, bool) else _SAFE_DEFAULT


def set_safe_mode(on: bool) -> dict[str, Any]:
    data = _state()
    data["safe_mode"] = bool(on)
    security.write_state(security.path(_STATE_FILE), data)
    try:
        security.append_line(security.path("audit.log"),
                             {"event": "privacy.safe_mode", "on": bool(on)})
    except Exception:
        pass
    return status()


def grant_task(action: str, seconds: int = 300) -> dict[str, Any]:
    """Authorize ONE kind of outward/mutating action for a short window. This is
    the 'task is planned / asked for' path: the user says yes, Vera may do that
    action until the window closes, then Safe Mode re-locks it."""
    import time
    data = _state()
    grants = data.get("grants") or {}
    grants[action] = time.time() + max(1, int(seconds))
    data["grants"] = grants
    security.write_state(security.path(_STATE_FILE), data)
    try:
        security.append_line(security.path("audit.log"),
                             {"event": "privacy.grant", "action": action, "seconds": seconds})
    except Exception:
        pass
    return {"granted": action, "until": grants[action]}


def _granted(action: str) -> bool:
    import time
    grants = _state().get("grants") or {}
    exp = grants.get(action)
    return bool(exp) and time.time() < float(exp)


def action_allowed(action: str) -> bool:
    """The everyday gate every outward/mutating capability consults. Read-only
    actions always pass. When Safe Mode is off, actions pass (lockdown still wins
    separately via security.guard). When Safe Mode is on, an action passes only if
    the user granted that task. Fail-closed: unknown/missing grant = blocked."""
    if security.is_locked():
        return False  # kill switch halts everything, regardless of Safe Mode
    if action in _READONLY:
        return True
    if not safe_mode():
        return True
    return _granted(action)


class SafeModeBlocked(Exception):
    """Raised by guard_action() when Safe Mode blocks an un-authorized action."""


def guard_action(action: str) -> None:
    """Capability modules call this before an outward/mutating action. Raises when
    Safe Mode blocks it, with a message that tells the user how to authorize it."""
    if not action_allowed(action):
        if security.is_locked():
            raise security.Locked(f"Vera is in lockdown — {action} is halted.")
        raise SafeModeBlocked(
            f"Safe Mode is on, so '{action}' needs your go-ahead first. "
            f"Authorize it, then I'll do it (it re-locks after).")


# ── the plain-language explainer (so the state is UNDERSTOOD, not guessed) ──────
def explain() -> dict[str, Any]:
    """A human, honest description of the CURRENT privacy posture — for the switch
    UI/menubar. Says exactly who can reach Vera and what's protecting her."""
    r = reach()
    locked = security.is_locked()
    if r == PRIVATE:
        who = "Only this Mac. No other device can reach Vera."
        reach_label = "🔒 Private (this Mac only)"
    else:
        who = ("Your devices, over Tailscale, with the device token. "
               "No one without the token gets in — not even on your tailnet.")
        reach_label = "📱 My devices (tailnet)"
    safe = safe_mode()
    return {
        "reach": r,
        "reach_label": reach_label,
        "who_can_reach": who,
        "token_set": token() is not None,
        "locked": locked,
        "lockdown_note": ("Lockdown is ON — Vera can't reach out or act, only think "
                          "on-device." if locked else "Lockdown is off."),
        "safe_mode": safe,
        "safe_mode_note": ("Safe Mode is on — Vera reads and chats freely, but asks "
                           "before any action that sends, writes, or controls."
                           if safe else
                           "Safe Mode is off — Vera may act without asking each time."),
        "bind_host": bind_host(),
    }


def status() -> dict[str, Any]:
    """Machine-readable state for the server/menubar/API."""
    return explain()
