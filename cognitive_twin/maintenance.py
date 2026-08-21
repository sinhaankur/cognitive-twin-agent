"""
maintenance — Vera keeps herself light. Runs on startup (once per launch) and:

  1. Compacts the plain, append-only projects store: rewrites projects.jsonl to
     the latest state per id, dropping dead history + duplicate lines. This is the
     "memory adapts + optimizes every time it opens" behaviour — the catalog stays
     current and small instead of growing forever.
  2. Reports Vera's on-disk footprint so "lightweight, doesn't destroy storage" is
     observable, not a hope.

Deliberately CONSERVATIVE + safe:
  • Never touches the SEALED memory store (memory.jsonl may be vault-encrypted per
    line — compacting it is the security kernel's job, not ours). We only compact
    the plain projects catalog.
  • Idempotent + cheap: a no-op when there's nothing to compact, so it never slows
    startup. Bounded, no network, no model calls.
  • Fail-soft: any error is swallowed — maintenance must never break a launch.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def _root() -> Path:
    return Path(os.environ.get("CTWIN_MEMORY_DIR", Path.home() / ".cognitive-twin"))


def _compact_projects() -> tuple[int, int]:
    """Rewrite projects.jsonl to one line per id (latest wins). Returns
    (lines_before, lines_after); a no-op returns equal counts."""
    path = _root() / "projects.jsonl"
    if not path.is_file():
        return (0, 0)
    try:
        raw = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    except OSError:
        return (0, 0)
    before = len(raw)
    latest: dict[str, dict] = {}
    order: list[str] = []
    for line in raw:
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        pid = e.get("id")
        if not pid:
            continue
        if pid not in latest:
            order.append(pid)
        latest[pid] = e  # later line overrides earlier — latest state wins
    after = len(latest)
    # Only rewrite if it actually shrinks — avoid needless disk writes.
    if after < before:
        tmp = path.with_suffix(".jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            for pid in order:
                fh.write(json.dumps(latest[pid], ensure_ascii=False) + "\n")
        os.replace(tmp, path)  # atomic
        try:
            os.chmod(path, 0o600)  # keep the store user-only, like the rest
        except OSError:
            pass
    return (before, after)


def _footprint_bytes() -> int:
    """Total bytes Vera stores under her home dir (excludes the heavy tts-venv,
    which is a Python venv, not memory)."""
    total = 0
    root = _root()
    if not root.exists():
        return 0
    for p in root.rglob("*"):
        try:
            if p.is_file() and "tts-venv" not in p.parts:
                total += p.stat().st_size
        except OSError:
            continue
    return total


def optimize(verbose: bool = False) -> str:
    """Run the startup self-optimization. Safe to call every launch."""
    try:
        before, after = _compact_projects()
    except Exception:
        before, after = (0, 0)
    saved = before - after
    footprint = _footprint_bytes()
    kb = footprint / 1024
    size = f"{kb:.0f} KB" if kb < 1024 else f"{kb/1024:.1f} MB"
    parts = []
    if saved > 0:
        parts.append(f"compacted projects catalog ({before}→{after} lines)")
    parts.append(f"memory footprint {size}")
    msg = "Vera optimized on start — " + "; ".join(parts) + "."
    if verbose:
        print(msg)
    return msg


# Run-once guard so importing this in multiple entry points doesn't double-run.
_DONE = False


def run_once(verbose: bool = False) -> None:
    global _DONE
    if _DONE:
        return
    _DONE = True
    optimize(verbose=verbose)
