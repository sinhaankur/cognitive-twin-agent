"""
applications — your job-application tracker, sealed on-device.

The system of record for a search: what you applied to, when, with which resume,
and where it stands. No cloud, no account — a sealed local log you own. Vera (or
you) can ask "what's outstanding?" and get an honest answer.

Statuses (a simple, real pipeline):
    saved → applied → screen → interview → offer → rejected / withdrawn

Each entry is sealed via the security kernel. Nothing is submitted anywhere — this
only records what YOU did.

CLI:
    python3 -m cognitive_twin.careers.applications add "Acme AI" "Senior AI Designer" [--resume ux] [--url ...]
    python3 -m cognitive_twin.careers.applications status <id> applied
    python3 -m cognitive_twin.careers.applications list [--open]
    python3 -m cognitive_twin.careers.applications note <id> "recruiter emailed"

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any

from .. import security

_DB = "applications.jsonl"

STATUSES = ["saved", "applied", "screen", "interview", "offer", "rejected", "withdrawn"]
_OPEN = {"saved", "applied", "screen", "interview", "offer"}


@dataclass
class Application:
    id: str
    company: str
    role: str
    status: str = "saved"
    resume: str = ""              # which resume variant you used
    url: str = ""
    created: str = ""
    updated: str = ""
    history: list[dict[str, str]] = field(default_factory=list)  # {at, status}
    notes: list[dict[str, str]] = field(default_factory=list)    # {at, text}


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _mk_id(company: str, role: str) -> str:
    h = hashlib.sha1(f"{company}|{role}|{_now()}".encode()).hexdigest()[:6]
    slug = "".join(c for c in company.lower() if c.isalnum())[:8]
    return f"{slug}-{h}"


# ── storage (sealed) ────────────────────────────────────────────────────────────
def _path():
    return security.path(_DB)


def read_all() -> list[Application]:
    out = []
    for data in security.read_lines(_path()):
        try:
            out.append(Application(**data))
        except Exception:
            continue
    return out


def _rewrite(apps: list[Application]) -> None:
    p = _path()
    p.unlink(missing_ok=True)
    for a in apps:
        security.append_line(p, asdict(a))


def get(app_id: str) -> Application | None:
    return next((a for a in read_all() if a.id == app_id), None)


# ── operations ──────────────────────────────────────────────────────────────────
def add(company: str, role: str, *, resume: str = "", url: str = "",
        status: str = "saved") -> Application:
    a = Application(id=_mk_id(company, role), company=company, role=role,
                    status=status, resume=resume, url=url,
                    created=_now(), updated=_now(),
                    history=[{"at": _now(), "status": status}])
    _rewrite(read_all() + [a])
    return a


def set_status(app_id: str, status: str) -> Application | None:
    if status not in STATUSES:
        raise ValueError(f"unknown status '{status}'. One of: {', '.join(STATUSES)}")
    apps = read_all()
    for a in apps:
        if a.id == app_id:
            a.status = status
            a.updated = _now()
            a.history.append({"at": _now(), "status": status})
            _rewrite(apps)
            return a
    return None


def add_note(app_id: str, text: str) -> Application | None:
    apps = read_all()
    for a in apps:
        if a.id == app_id:
            a.notes.append({"at": _now(), "text": text})
            a.updated = _now()
            _rewrite(apps)
            return a
    return None


def remove(app_id: str) -> bool:
    apps = read_all()
    keep = [a for a in apps if a.id != app_id]
    if len(keep) == len(apps):
        return False
    _rewrite(keep)
    return True


# ── views ───────────────────────────────────────────────────────────────────────
def open_apps() -> list[Application]:
    return [a for a in read_all() if a.status in _OPEN]


def summary() -> str:
    apps = read_all()
    if not apps:
        return "No applications tracked yet. Add one: `applications add \"Company\" \"Role\"`."
    from collections import Counter
    counts = Counter(a.status for a in apps)
    head = f"{len(apps)} application(s): " + " · ".join(f"{counts[s]} {s}" for s in STATUSES if counts[s])
    lines = [head, ""]
    for a in sorted(apps, key=lambda x: x.updated, reverse=True):
        tag = f" [{a.resume}]" if a.resume else ""
        lines.append(f"  {a.id:<16} {a.status:<10} {a.company} — {a.role}{tag}")
    return "\n".join(lines)


# ── CLI ─────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "list"
    args = argv[1:]

    def opt(flag, default=""):
        return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else default

    if cmd == "add":
        pos = [a for a in args if not a.startswith("--")]
        # remove option values from positionals
        for flag in ("--resume", "--url", "--status"):
            v = opt(flag)
            if v in pos:
                pos.remove(v)
        if len(pos) < 2:
            print('usage: add "Company" "Role" [--resume NAME] [--url URL]'); return 2
        a = add(pos[0], pos[1], resume=opt("--resume"), url=opt("--url"),
                status=opt("--status", "saved"))
        print(f"✓ tracked {a.id}: {a.company} — {a.role} ({a.status})"); return 0
    if cmd == "status":
        if len(args) < 2:
            print("usage: status <id> <" + "|".join(STATUSES) + ">"); return 2
        try:
            a = set_status(args[0], args[1])
        except ValueError as e:
            print(f"✗ {e}"); return 1
        print(f"✓ {a.id} → {a.status}" if a else "not found"); return 0 if a else 1
    if cmd == "note":
        if len(args) < 2:
            print('usage: note <id> "text"'); return 2
        a = add_note(args[0], " ".join(args[1:]))
        print("✓ noted" if a else "not found"); return 0 if a else 1
    if cmd == "remove":
        print("✓ removed" if args and remove(args[0]) else "not found"); return 0
    if cmd == "list":
        if "--open" in args:
            apps = open_apps()
            print("\n".join(f"  {a.id:<16} {a.status:<10} {a.company} — {a.role}"
                            for a in apps) or "No open applications."); return 0
        print(summary()); return 0
    print("usage: applications [add|status|note|list|remove]")
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
