"""
security — the kernel. Everything personal Vera stores goes through here, sealed.

Ankur's directive: *everything secured on this app, like a kernel.* So this module
is the single guarded path to disk for personal data. No feature writes your life
to a file directly; it calls ``write_state`` / ``append_line`` here, and those
ALWAYS seal at rest with the device-bound key from ``vault.py`` (ChaCha20-Poly1305,
key held in the macOS Keychain, bound to this Mac + this account). Copy any of
Vera's files to another machine and they read as noise.

Why a kernel and not "each module seals itself": if sealing is optional per
module, one forgotten call leaks your data in plaintext (exactly what we found —
activity/mood/rhythms/soul were plaintext). Routing every store through one API
makes "secured" the default and the *only* path, not a thing to remember.

Two storage shapes, both sealed:
  • STATE  — a single JSON document (mood flags, rhythms, soul, activity summary).
             ``write_state(path, obj)`` / ``read_state(path, default)``.
  • LOG    — an append-only JSONL of records (activity samples, visits, emails).
             ``append_line(path, obj)`` / ``read_lines(path)``.

Self-healing migration: readers transparently accept a legacy *plaintext* file and
re-seal it on the next write, so turning the kernel on never loses old data. Run
``python3 -m cognitive_twin.security seal-all`` to seal everything now.

Owner-only permissions (0600) are enforced on every file we create.

Honest threat model (same as vault.py): at-rest sealing protects the files —
backups, a copied disk, another account. It does not protect against code running
as you on an unlocked session; that is the OS's job. We don't pretend otherwise.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Iterable

from . import vault

_OWNER_ONLY = stat.S_IRUSR | stat.S_IWUSR  # 0600


# ── the memory root (one place, mirrors the rest of the app) ───────────────────
def home() -> Path:
    root = Path(os.environ.get("CTWIN_MEMORY_DIR", Path.home() / ".cognitive-twin"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def path(name: str) -> Path:
    """Resolve a store name to its file under the memory root."""
    return home() / name


def _chmod_owner(p: Path) -> None:
    try:
        os.chmod(p, _OWNER_ONLY)
    except OSError:
        pass


def _atomic_write_bytes(p: Path, data: bytes) -> None:
    """Write via a temp file + replace so a crash never leaves a half file."""
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(data)
    _chmod_owner(tmp)
    tmp.replace(p)
    _chmod_owner(p)


# ── STATE: a single sealed JSON document ───────────────────────────────────────
def write_state(p: Path | str, obj: Any) -> None:
    """Seal a JSON document to ``p`` (atomic, owner-only). The only way personal
    state should reach disk."""
    p = Path(p)
    blob = vault.seal_bytes(json.dumps(obj, ensure_ascii=False).encode("utf-8"))
    _atomic_write_bytes(p, blob)


def read_state(p: Path | str, default: Any = None) -> Any:
    """Read a sealed JSON document. Transparently accepts a legacy *plaintext*
    file (and leaves it for the next write to re-seal). Returns ``default`` if
    absent or unreadable on this device."""
    p = Path(p)
    if not p.is_file():
        return default
    raw = p.read_bytes()
    try:
        data = vault.open_bytes(raw) if vault.is_sealed_bytes(raw) else raw
        return json.loads(data)
    except Exception:
        return default


# ── LOG: append-only sealed JSONL ──────────────────────────────────────────────
def append_line(p: Path | str, obj: Any) -> None:
    """Append one sealed JSONL record (owner-only). For activity/visits/emails."""
    p = Path(p)
    line = vault.seal_line(json.dumps(obj, ensure_ascii=False))
    newfile = not p.exists()
    with p.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    if newfile:
        _chmod_owner(p)


def read_lines(p: Path | str) -> list[Any]:
    """Read a sealed (or legacy plaintext) JSONL log into a list of objects.
    Skips any single corrupt/foreign line rather than failing the whole read."""
    p = Path(p)
    if not p.is_file():
        return []
    out: list[Any] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = vault.open_line(raw) if vault.is_sealed_line(raw) else raw
            out.append(json.loads(data))
        except Exception:
            continue
    return out


# ── one-shot: seal everything that's currently plaintext ───────────────────────
# The personal stores the kernel owns. STATE files are single JSON docs; LOG
# files are JSONL. This list is the audit surface — if a new personal store is
# added, it belongs here so `seal-all` and `audit` cover it.
STATE_STORES = [
    "activity_state.json",  # activity.py enable/pause state
    "mood.json",
    "rhythms.json",
    "soul.json",
    "persona.json",
]
LOG_STORES = [
    "activity.jsonl",
    "places.jsonl",
    "mail.jsonl",
]


def _reseal_state_file(p: Path) -> bool:
    if not p.is_file():
        return False
    raw = p.read_bytes()
    if vault.is_sealed_bytes(raw):
        return False
    try:
        obj = json.loads(raw)
    except Exception:
        return False
    write_state(p, obj)
    return True


def seal_all() -> dict[str, int]:
    """Seal every currently-plaintext personal store in place. Idempotent."""
    sealed_state = 0
    for name in STATE_STORES:
        if _reseal_state_file(path(name)):
            sealed_state += 1
    sealed_lines = 0
    for name in LOG_STORES:
        sealed_lines += vault.migrate_jsonl(path(name))
    return {"state_files_sealed": sealed_state, "log_lines_sealed": sealed_lines}


def audit() -> list[tuple[str, str]]:
    """Report each known store's at-rest state: sealed / plaintext / absent /
    bad-perms. This is the 'is everything actually secured?' check."""
    rows: list[tuple[str, str]] = []

    def perms_ok(p: Path) -> bool:
        try:
            return (p.stat().st_mode & 0o077) == 0  # no group/other access
        except OSError:
            return True

    for name in STATE_STORES:
        p = path(name)
        if not p.is_file():
            rows.append((name, "absent"))
            continue
        raw = p.read_bytes()
        state = "sealed" if vault.is_sealed_bytes(raw) else "PLAINTEXT"
        if not perms_ok(p):
            state += " + world-readable!"
        rows.append((name, state))

    for name in LOG_STORES:
        p = path(name)
        if not p.is_file():
            rows.append((name, "absent"))
            continue
        lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if not lines:
            rows.append((name, "empty"))
            continue
        n_plain = sum(0 if vault.is_sealed_line(ln.strip()) else 1 for ln in lines)
        state = "sealed" if n_plain == 0 else f"{n_plain}/{len(lines)} PLAINTEXT line(s)"
        if not perms_ok(p):
            state += " + world-readable!"
        rows.append((name, state))
    return rows


# ── CLI ─────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "audit"
    if cmd == "seal-all":
        r = seal_all()
        print(f"✓ Sealed {r['state_files_sealed']} state file(s) and "
              f"{r['log_lines_sealed']} log line(s). Everything at rest is now "
              f"noise off this Mac.")
        return 0
    if cmd == "audit":
        print("At-rest security audit (~/.cognitive-twin):\n")
        worst = "sealed"
        for name, state in audit():
            mark = "✓" if state in ("sealed", "absent", "empty") else "⚠"
            if "PLAINTEXT" in state or "world-readable" in state:
                worst = "unsealed"
            print(f"  {mark} {name:<22} {state}")
        print()
        if worst == "unsealed":
            print("⚠ Some personal data is plaintext. Run "
                  "`python3 -m cognitive_twin.security seal-all` to seal it.")
        else:
            print("✓ Everything Vera stores is sealed and owner-only.")
        return 0
    print("usage: python3 -m cognitive_twin.security [audit|seal-all]")
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
