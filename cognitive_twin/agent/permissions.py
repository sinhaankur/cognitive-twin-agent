"""
permissions — the safety spine for Vera's agent loop.

Every tool the agent might run is put in a RISK CLASS, and a PERMISSION MODE
decides whether that class runs freely, must ask first, or is blocked. This is
how Vera gets "Claude-level" capability without losing the founding guarantee:
**Vera never acts on its own unless you turn that on.**

Modes (see docs/VERA-AGENT.md):
    read_only  — only `read` tools run. Nothing writes/sends/leaves the machine.
    approve    — acting tools run only after an explicit yes, one at a time. (default)
    auto       — allow-listed acting tools run without asking (opt-in autonomy),
                 still bounded by the loop's step/time budgets + kill-switch.

Risk classes:
    read          — reads local/allowed data, changes nothing (calendar, contacts…)
    write_local   — writes to Vera's own sealed store (note a task, set rhythm)
    network       — reaches the internet (gated further by net.py's allow-list)
    act_external  — sends/books/posts/deletes in the outside world (the booker,
                    email send) — the highest bar; always stops unless auto+allowed.

The mode + risk decide one of: RUN · ASK · BLOCK. The agent loop enforces it at
the single dispatch point, and every decision is auditable.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from .. import security


class Decision(str, Enum):
    RUN = "run"
    ASK = "ask"
    BLOCK = "block"


_MODES = ("read_only", "approve", "auto")
_POLICY_FILE = "agent_policy.json"

# Explicit risk classification by skill name. Anything not listed defaults to
# `read` ONLY if its name looks read-ish; otherwise it's treated as write_local
# (safe side). Acting skills MUST be listed here — we never silently treat an
# unknown skill as safe to act with.
_RISK: dict[str, str] = {
    # reads
    "now": "read", "calendar_agenda": "read", "calendar_next": "read",
    "calendar_free": "read", "contacts_search": "read", "contacts_count": "read",
    "contacts_review": "read", "day_shape": "read", "my_day": "read",
    "analyze_sentiment": "read", "list_projects": "read", "list_dir": "read",
    "read_file": "read", "daily_digest": "read", "web_search": "read",
    # local writes (Vera's own sealed store)
    "note_task": "write_local", "complete_task": "write_local",
    "set_daily_commitment": "write_local",
    # network
    "web_fetch": "network", "web_download": "network",
    # external actions (the high bar)
    "book_amenity": "act_external", "send_email": "act_external",
    "post_message": "act_external", "run_dev_command": "act_external",
}

# In `auto` mode, only these skills may act WITHOUT asking (the opt-in autonomy
# allow-list). Empty by default — you add to it deliberately.
_AUTO_ALLOW_DEFAULT: list[str] = []


def _policy() -> dict[str, Any]:
    d = security.read_state(security.path(_POLICY_FILE), default=None)
    if not isinstance(d, dict):
        d = {"mode": "approve", "auto_allow": list(_AUTO_ALLOW_DEFAULT)}
        security.write_state(security.path(_POLICY_FILE), d)
    return d


def _save(d: dict[str, Any]) -> None:
    security.write_state(security.path(_POLICY_FILE), d)


def mode() -> str:
    return _policy().get("mode", "approve")


def set_mode(m: str) -> str:
    m = (m or "").strip().lower()
    if m not in _MODES:
        return f"Mode must be one of: {', '.join(_MODES)}."
    d = _policy(); d["mode"] = m; _save(d)
    return {"read_only": "Read-only — I'll only read, never act.",
            "approve": "Approve-each — I'll ask before any action.",
            "auto": "Autonomous — allow-listed actions run without asking (kill-switch stays live)."}[m]


def risk_of(skill_name: str) -> str:
    if skill_name in _RISK:
        return _RISK[skill_name]
    # Unknown skill: infer read from the name, else treat as write_local (never
    # silently assume it's safe to act).
    low = skill_name.lower()
    if any(low.startswith(p) for p in ("read", "list", "get", "show", "search", "find", "analyze", "count", "next", "status")):
        return "read"
    return "write_local"


def auto_allow(skill_name: str) -> str:
    d = _policy()
    if skill_name not in d.get("auto_allow", []):
        d.setdefault("auto_allow", []).append(skill_name); _save(d)
    return f"'{skill_name}' may now run without asking in autonomous mode."


def decide(skill_name: str, *, approved: bool = False) -> tuple[Decision, str]:
    """The gate. Given the current mode + the skill's risk, decide RUN/ASK/BLOCK
    and a human reason. `approved` = the user already said yes to this one call."""
    m = mode()
    risk = risk_of(skill_name)

    if risk == "read":
        return Decision.RUN, "read-only tool"

    if m == "read_only":
        return Decision.BLOCK, f"read-only mode blocks '{skill_name}' ({risk}). Switch to approve/auto to allow it."

    if approved:
        return Decision.RUN, "you approved this action"

    if m == "auto":
        allow = _policy().get("auto_allow", [])
        if risk in ("write_local", "network") or skill_name in allow:
            return Decision.RUN, "autonomous mode (allow-listed)"
        # act_external not on the allow-list still asks, even in auto
        return Decision.ASK, f"'{skill_name}' is an external action not on the auto allow-list — confirm it."

    # approve mode, not yet approved
    return Decision.ASK, f"'{skill_name}' ({risk}) needs your ok before it runs."


def status() -> str:
    d = _policy()
    return (f"Agent permission: mode = {d['mode']}. "
            f"Auto-allow ({len(d.get('auto_allow', []))}): "
            + (", ".join(d.get("auto_allow", [])) or "none") + ".")
