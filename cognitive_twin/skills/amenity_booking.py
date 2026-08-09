"""
amenity_booking — a Vera skill that books a building amenity on BuildingLink.

Vera shells out to the standalone Node/Playwright booker at
~/Documents/buildinglink-booker (Ankur's personal project) and returns its
structured RESULT. The booker owns the browser automation + the rule that it
picks a RANDOM afternoon/evening slot; this skill is just the bridge so Vera can
run it on Ankur's behalf ("check availability and book it for me").

Safety: mirrors the booker's own dry-run gate — Vera can CHECK availability
freely, but an actual booking only happens when the booker's config.confirmBookings
is true (Ankur flips that once calibrated). Vera never edits that flag.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .base import default_registry as R

# Where the standalone booker lives. Override with BOOKER_DIR if it moves.
BOOKER_DIR = Path(os.environ.get("BOOKER_DIR", Path.home() / "Documents" / "buildinglink-booker"))


def _run_booker(extra_args: list[str], timeout_s: int = 300) -> str:
    """Run the Node booker and return its RESULT JSON (or a clear error string)."""
    if not (BOOKER_DIR / "src" / "book.mjs").exists():
        return f"[error] booker not found at {BOOKER_DIR}. Is buildinglink-booker installed?"
    node = _which("node")
    if not node:
        return "[error] node is not installed / not on PATH."
    try:
        proc = subprocess.run(
            [node, str(BOOKER_DIR / "src" / "book.mjs"), *extra_args],
            cwd=str(BOOKER_DIR),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env={**os.environ, "HEADFUL": os.environ.get("HEADFUL", "false")},
        )
    except subprocess.TimeoutExpired:
        return f"[error] booker timed out after {timeout_s}s."
    # The booker prints one `RESULT: {json}` line; surface that.
    for line in reversed((proc.stdout + "\n" + proc.stderr).splitlines()):
        if line.startswith("RESULT:"):
            return line[len("RESULT:"):].strip()
    return f"[error] booker produced no RESULT (exit {proc.returncode}). stderr tail: {proc.stderr[-300:]}"


def _which(cmd: str) -> str | None:
    from shutil import which
    return which(cmd)


def _humanize(result_json: str) -> str:
    """Turn the booker's RESULT JSON into a sentence Vera can say back."""
    try:
        r = json.loads(result_json)
    except Exception:
        return result_json  # already an [error] string
    status = r.get("status")
    if status == "booked":
        b = r.get("booked", {})
        return f"Booked {b.get('amenity')} on {b.get('date')} at {b.get('time')} — confirmed."
    if status == "booked-unverified":
        b = r.get("booked", {})
        # Honest: the Save click went through but the confirmation page wasn't
        # seen. Never tell Ankur it's booked when we couldn't verify it.
        return (f"I clicked through for {b.get('amenity')} on {b.get('date')} at "
                f"{b.get('time')}, but couldn't confirm the reservation page — "
                f"please double-check it actually took.")
    if status == "dry-run":
        w = r.get("wouldBook", {})
        return (f"Dry run — would book {w.get('amenity')} on {w.get('date')} at "
                f"{w.get('time')} (out of {r.get('eligibleCount')} open slots). "
                f"Enable confirmBookings in the booker to make it real.")
    if status == "none-available":
        return "No open slots for any target amenity across the next week right now."
    if status == "listed":
        rows = r.get("eligible", [])
        if not rows:
            return "No eligible afternoon/evening slots found."
        lines = [f"- {x['amenity']} · {x['date']} · {x['time']}" for x in rows[:15]]
        return "Open afternoon/evening slots:\n" + "\n".join(lines)
    if status == "error":
        return f"The booker hit an error: {r.get('error')}"
    return result_json


@R.add(
    "check_amenity_availability",
    "Check BuildingLink for open amenity slots (Ping Pong Table 1, Tennis, Squash) "
    "across the next week WITHOUT booking. Read-only.",
)
def check_amenity_availability() -> str:
    return _humanize(_run_booker(["--list-only"]))


@R.add(
    "book_amenity",
    "Book a building amenity on BuildingLink (Ping Pong Table 1, Tennis, or Squash). "
    "Scans the next week and picks a RANDOM open slot honouring each amenity's "
    "preferred time window + preferred days (Tennis→weekends, Ping Pong→weekdays), "
    "then verifies the confirmation. Actually books only if the booker's "
    "confirmBookings is enabled; otherwise it's a safe dry run.",
)
def book_amenity() -> str:
    return _humanize(_run_booker([]))
