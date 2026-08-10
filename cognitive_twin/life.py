"""
life — one place that tracks everything, with NO assistant required.

This is the unifying tracker: it pulls together every on-device signal Vera can
collect — where you went, your inbox accounts, your social activity, your job
applications, your amenity bookings — into a single status a person can read. It
imports only the standalone modules (no voice/agent stack), so it works whether or
not the Vera app is installed. It's the data layer behind the standalone dashboard
and the `life` command.

Everything it reads is sealed on-device; it never fetches or sends anything.

CLI:
    python3 -m cognitive_twin.life status        # one-screen "how's everything?"
    python3 -m cognitive_twin.life json           # machine-readable (for the dashboard)

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import json
from typing import Any


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


# ── each area reports a small, uniform summary dict ────────────────────────────
def _places_summary() -> dict[str, Any]:
    from . import places
    if not places.is_enabled():
        return {"on": False, "headline": "Location tracking off"}
    today = places.today()
    return {"on": True,
            "headline": (f"{len(today)} place(s) today" if today else "No places logged today"),
            "detail": places.summarize_day(today, label="today") if today else "",
            "count": len(places.read_all())}


def _email_summary() -> dict[str, Any]:
    from . import mail_store
    try:
        from . import account_inventory as A
    except Exception:
        A = None
    n = _safe(mail_store.count, 0) or 0
    if n == 0:
        return {"on": False, "headline": "No inbox indexed yet"}
    out = {"on": True, "headline": f"{n} email(s) indexed"}
    if A:
        sug = _safe(lambda: A.suggestions(), {}) or {}
        useless = len(sug.get("unsubscribe", []))
        unused = len(sug.get("close_or_cancel", []))
        if useless or unused:
            out["detail"] = f"{unused} account(s) to close, {useless} to unsubscribe"
    return out


def _social_summary() -> dict[str, Any]:
    from . import social
    if not social.is_enabled():
        return {"on": False, "headline": "Social tracking off"}
    items = _safe(social.read_all, []) or []
    if not items:
        return {"on": True, "headline": "No social data imported yet"}
    act = _safe(lambda: social.activity_over_time(30), {}) or {}
    sent = _safe(lambda: social.sentiment_trend(30), {}) or {}
    head = f"{act.get('total', 0)} action(s) in 30d"
    detail = ""
    if sent.get("avg") is not None:
        mood = "positive" if sent["avg"] > 0.1 else "negative" if sent["avg"] < -0.1 else "neutral"
        detail = f"tone of your posts: {mood} ({sent['avg']:+.2f})"
    return {"on": True, "headline": head, "detail": detail}


def _careers_summary() -> dict[str, Any]:
    from .careers import resumes, applications
    rs = _safe(resumes.read_all, []) or []
    apps = _safe(applications.read_all, []) or []
    open_apps = _safe(applications.open_apps, []) or []
    if not rs and not apps:
        return {"on": False, "headline": "No resumes or applications yet"}
    return {"on": True,
            "headline": f"{len(open_apps)} open application(s)",
            "detail": f"{len(rs)} resume(s) on file, {len(apps)} tracked total"}


def _booker_summary() -> dict[str, Any]:
    """Read the booker's history/last-result (separate repo) without importing it."""
    import os
    from pathlib import Path
    root = Path(os.environ.get("BOOKER_DIR", Path.home() / "Documents" / "buildinglink-booker"))
    hist = root / "history.jsonl"
    if not hist.is_file():
        last = root / "last-result.json"
        if last.is_file():
            r = _safe(lambda: json.loads(last.read_text()), {}) or {}
            return {"on": True, "headline": f"Last run: {r.get('status', 'unknown')}"}
        return {"on": False, "headline": "Booker not set up"}
    rows = [json.loads(l) for l in hist.read_text().splitlines() if l.strip()]
    booked = [r for r in rows if r.get("status", "").startswith("booked")]
    return {"on": True,
            "headline": f"{len(booked)} booking(s) logged",
            "detail": "; ".join(f"{b['booked']['amenity']} {b['booked']['date']}"
                                for b in booked[-3:] if b.get("booked"))}


AREAS = [
    ("places", "Where you go", _places_summary),
    ("email", "Inbox & accounts", _email_summary),
    ("social", "Social activity", _social_summary),
    ("careers", "Job search", _careers_summary),
    ("booker", "Amenity bookings", _booker_summary),
]


def snapshot() -> list[dict[str, Any]]:
    out = []
    for key, title, fn in AREAS:
        s = _safe(fn, {"on": False, "headline": "unavailable"}) or {}
        out.append({"key": key, "title": title, **s})
    return out


def status_text() -> str:
    lines = ["Your life — everything tracked on this Mac:\n"]
    for a in snapshot():
        mark = "●" if a.get("on") else "○"
        lines.append(f"  {mark} {a['title']}: {a.get('headline', '')}")
        if a.get("detail"):
            lines.append(f"      {a['detail']}")
    lines.append("\n(All sealed on-device. Nothing here left your machine.)")
    return "\n".join(lines)


# ── CLI ─────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "json":
        print(json.dumps(snapshot(), indent=2)); return 0
    if cmd == "status":
        print(status_text()); return 0
    print("usage: python3 -m cognitive_twin.life [status|json]")
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
