"""
controls — one source of truth for every automation/data-source toggle.

This is the *logic* behind the control panel, and it stands alone: it works as a
plain script even if Vera (the assistant/UI) isn't running. Vera's web panel and
CLI both just call into here; nothing about a toggle lives inside the UI. That's
the rule — capabilities are standalone modules, the panel is only a front-end.

Each control has: a stable `key`, a human `label`, a `group`, a `state` getter,
and a `set(on)` setter, plus whether it's currently `available` on this machine.
Reading never changes anything; setting flips exactly one control.

CLI:
    python3 -m cognitive_twin.controls list                 # all controls + state
    python3 -m cognitive_twin.controls on  <key>
    python3 -m cognitive_twin.controls off <key>
    python3 -m cognitive_twin.controls json                 # machine-readable (for UIs)

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Control:
    key: str
    label: str
    group: str
    get: Callable[[], bool]
    set: Callable[[bool], None]
    description: str = ""
    available: Callable[[], bool] = lambda: True
    # Some controls are informational/read-only (e.g. "email connected") — no set.
    readonly: bool = False

    def snapshot(self) -> dict[str, Any]:
        try:
            on = bool(self.get())
        except Exception:
            on = False
        try:
            avail = bool(self.available())
        except Exception:
            avail = False
        return {"key": self.key, "label": self.label, "group": self.group,
                "on": on, "available": avail, "readonly": self.readonly,
                "description": self.description}


# ── lazy accessors (import modules only when touched, so a missing optional dep
#    never breaks the whole panel) ──────────────────────────────────────────────
def _safe(fn, default=False):
    try:
        return fn()
    except Exception:
        return default


def _registry() -> list[Control]:
    controls: list[Control] = []

    # — Vera senses / data sources —
    def _mod(name):
        import importlib
        return importlib.import_module(f"cognitive_twin.{name}")

    # Activity (screen work patterns)
    controls.append(Control(
        "activity", "Activity awareness", "Vera — senses",
        get=lambda: _safe(lambda: _mod("activity").is_enabled()),
        set=lambda on: _mod("activity").enable(on),
        description="Notice which apps you work in, on-device.",
    ))
    # Mood / reflective tone
    controls.append(Control(
        "mood", "Reflective mood", "Vera — senses",
        get=lambda: _safe(lambda: _mod("mood").is_on()),
        set=lambda on: _mod("mood").set_on(on),
        description="Warmer, reflective replies.",
    ))
    # Places / location
    controls.append(Control(
        "places", "Location tracking", "Vera — senses",
        get=lambda: _safe(lambda: _mod("places").is_enabled()),
        set=lambda on: (_mod("places").enable() if on else _mod("places").disable()),
        description="Where you go, from your own data — sealed on this Mac.",
    ))
    # Social (Meta)
    controls.append(Control(
        "social", "Social (Facebook/Instagram)", "Vera — senses",
        get=lambda: _safe(lambda: _mod("social").is_enabled()),
        set=lambda on: (_mod("social").enable() if on else _mod("social").disable()),
        description="From your Meta export — activity + on-device sentiment.",
    ))

    # — Vera capabilities —
    controls.append(Control(
        "screen_control", "Screen control", "Vera — capabilities",
        get=lambda: _safe(lambda: _mod("control").is_enabled()),
        set=lambda on: _mod("control").enable(on),
        description="See the screen + take named, confirmable actions.",
    ))
    # Careers assistant AI switch — the tool works fully WITHOUT this (deterministic
    # parsing + fit scoring); ON adds local-LLM phrasing for tailoring/cover letters.
    controls.append(Control(
        "careers_ai", "Careers: AI phrasing", "Vera — capabilities",
        get=_careers_ai_get, set=_careers_ai_set,
        description="Human-in-the-loop resume/job tools work without AI; switch on "
                    "for smarter local-LLM phrasing (opt-in).",
    ))

    # — Connections (read-only status) —
    controls.append(Control(
        "email_connected", "Email connected", "Connections",
        get=lambda: _safe(lambda: _mod("secrets_store").has("IMAP_PASSWORD")),
        set=lambda on: None, readonly=True,
        description="Gmail app password stored in the Keychain.",
    ))

    # — The amenity booker (separate repo/script) —
    controls.append(Control(
        "booker_confirm", "Booker: real bookings", "Automations — amenity booker",
        get=_booker_confirm_get, set=_booker_confirm_set,
        available=_booker_available,
        description="OFF = dry-run (finds slots, never books). ON = will make real "
                    "reservations. Leave off unless you mean it.",
    ))
    controls.append(Control(
        "booker_nightly", "Booker: nightly auto-run", "Automations — amenity booker",
        get=_booker_nightly_get, set=_booker_nightly_set,
        available=_booker_available,
        description="Scheduled nightly booking via launchd.",
    ))

    return controls


# ── booker bridges (it's a separate Node project; we edit its config + launchd) ─
from pathlib import Path
import os
import re
import subprocess

_BOOKER_DIR = Path(os.environ.get("BOOKER_DIR", Path.home() / "Documents" / "buildinglink-booker"))
_BOOKER_CONFIG = _BOOKER_DIR / "src" / "config.mjs"
_LAUNCHD_LABEL = "com.sinhaankur.buildinglink-booker"
_LAUNCHD_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{_LAUNCHD_LABEL}.plist"


def _careers_ai_flag() -> Path:
    from . import security
    return security.home() / "careers.ai_enabled"


def _careers_ai_get() -> bool:
    return _careers_ai_flag().is_file()


def _careers_ai_set(on: bool) -> None:
    f = _careers_ai_flag()
    if on:
        f.write_text("1", encoding="utf-8")
    else:
        f.unlink(missing_ok=True)


def _booker_available() -> bool:
    return _BOOKER_CONFIG.is_file()


def _booker_confirm_get() -> bool:
    if not _BOOKER_CONFIG.is_file():
        return False
    txt = _BOOKER_CONFIG.read_text(encoding="utf-8")
    m = re.search(r"confirmBookings:\s*(true|false)", txt)
    return bool(m and m.group(1) == "true")


def _booker_confirm_set(on: bool) -> None:
    if not _BOOKER_CONFIG.is_file():
        return
    txt = _BOOKER_CONFIG.read_text(encoding="utf-8")
    txt = re.sub(r"confirmBookings:\s*(true|false)",
                 f"confirmBookings: {'true' if on else 'false'}", txt)
    _BOOKER_CONFIG.write_text(txt, encoding="utf-8")


def _booker_nightly_get() -> bool:
    return _LAUNCHD_PLIST.is_file()


def _booker_nightly_set(on: bool) -> None:
    script = _BOOKER_DIR / "scripts" / "install-nightly.sh"
    if not script.is_file():
        return
    arg = [] if on else ["uninstall"]
    try:
        subprocess.run(["bash", str(script), *arg], cwd=str(_BOOKER_DIR),
                       capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        pass


# ── public API (what the CLI + web panel call) ─────────────────────────────────
def snapshot() -> list[dict[str, Any]]:
    """Every control's current state, grouped-friendly, for a UI."""
    return [c.snapshot() for c in _registry()]


def get_control(key: str) -> Control | None:
    return next((c for c in _registry() if c.key == key), None)


def set_control(key: str, on: bool) -> dict[str, Any]:
    """Flip one control. Returns its new snapshot, or an error dict."""
    c = get_control(key)
    if c is None:
        return {"error": f"unknown control '{key}'"}
    if c.readonly:
        return {"error": f"'{key}' is read-only"}
    if not _safe(c.available):
        return {"error": f"'{key}' isn't available on this machine"}
    try:
        c.set(bool(on))
    except Exception as e:
        return {"error": f"failed to set '{key}': {e}"}
    return c.snapshot()


# ── CLI ─────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "list"
    if cmd == "json":
        print(json.dumps(snapshot(), indent=2)); return 0
    if cmd == "list":
        group = None
        for c in snapshot():
            if c["group"] != group:
                group = c["group"]; print(f"\n{group}")
            mark = "●" if c["on"] else "○"
            avail = "" if c["available"] else "  (unavailable)"
            ro = "  [read-only]" if c["readonly"] else ""
            print(f"  {mark} {c['label']:<32} {c['key']}{avail}{ro}")
        print()
        return 0
    if cmd in ("on", "off"):
        if len(argv) < 2:
            print(f"usage: {cmd} <key>"); return 2
        r = set_control(argv[1], cmd == "on")
        if "error" in r:
            print(f"✗ {r['error']}"); return 1
        print(f"✓ {r['label']}: {'on' if r['on'] else 'off'}"); return 0
    print("usage: python3 -m cognitive_twin.controls [list|json|on <key>|off <key>]")
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
