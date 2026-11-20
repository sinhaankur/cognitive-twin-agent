"""
backup — durable, automatic, sealed backups of Vera's whole vault.

The vault (life story, keepsakes, persona, memory, voice) is the inheritance core —
the irreplaceable part. On-device sealing protects it at REST, but a single Mac can
be lost, wiped, or die. This module keeps a sealed copy somewhere that outlives the
machine, automatically, so a memory you pour in is safe the moment you add it.

Design:
  * The backup is one portable, passphrase-encrypted bundle (vault.export_bundle —
    ChaCha20-Poly1305 over the whole memory folder). It's already ciphertext before
    it leaves the vault, so wherever it lands only ever holds noise.
  * Default destination = iCloud Drive (scoped to YOUR Apple ID → off-Mac, survives a
    dead Mac, syncs for free). Falls back to a local folder if iCloud isn't present.
    Override with CTWIN_BACKUP_DIR.
  * The backup PASSPHRASE is a random key kept in the macOS Keychain (device-bound),
    so routine backups need no typing — but you can print it (`ctwin backup key`) and
    keep it somewhere safe, because restoring on a NEW Mac needs it.
  * ROTATION: keeps the newest few dated copies, so one bad/partial write can never
    clobber your last good backup.

Nothing is uploaded by us — we write a sealed file to a folder you control. iCloud
(if used) is your own Apple ID.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from . import vault

_KEEP = 7                       # dated copies to retain per destination
_KC_SERVICE = "cognitive-twin-backup-key"


# ── where backups live ────────────────────────────────────────────────────────
def backup_dir() -> Path:
    """The backup destination. CTWIN_BACKUP_DIR wins; else iCloud Drive (off-Mac,
    survives a dead Mac); else a local folder. Created if missing."""
    env = os.environ.get("CTWIN_BACKUP_DIR")
    if env:
        d = Path(env).expanduser()
    else:
        icloud = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
        d = (icloud / "Vera Backups") if icloud.is_dir() else (Path.home() / ".cognitive-twin-backups")
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_offsite() -> bool:
    """True when backups land in iCloud (survive this Mac) vs. a same-disk folder."""
    return "Mobile Documents" in str(backup_dir())


# ── the backup passphrase — a device-bound key in the Keychain ────────────────
def _keychain_get() -> str | None:
    try:
        r = subprocess.run(["security", "find-generic-password", "-s", _KC_SERVICE, "-w"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _keychain_set(key: str) -> bool:
    try:
        r = subprocess.run(["security", "add-generic-password", "-a", os.environ.get("USER", "vera"),
                            "-s", _KC_SERVICE, "-w", key, "-U"], capture_output=True, timeout=5)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def backup_key() -> str:
    """The backup passphrase. Created once (32 random hex chars) and kept in the
    Keychain. KEEP A COPY (`ctwin backup key`) — restoring on a NEW Mac needs it."""
    k = _keychain_get()
    if k:
        return k
    k = secrets.token_hex(16)
    _keychain_set(k)   # best-effort; if the Keychain is unavailable the key still works this run
    return k


# ── run a backup ──────────────────────────────────────────────────────────────
def run() -> dict[str, Any]:
    """Export a fresh sealed bundle to the backup dir, dated, and prune old copies.
    Returns a small status dict; never raises for a routine call."""
    try:
        dest_dir = backup_dir()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out = dest_dir / f"vera-vault-{stamp}.ctwin"
        info = vault.export_bundle(out, backup_key())
        _prune(dest_dir)
        # a 'latest' convenience copy (atomic replace) so restore is one obvious file
        latest = dest_dir / "vera-vault-latest.ctwin"
        tmp = latest.with_suffix(".ctwin.tmp")
        tmp.write_bytes(out.read_bytes())
        tmp.replace(latest)
        return {"ok": True, "path": str(out), "files": info.get("files"),
                "offsite": is_offsite(), "dir": str(dest_dir), "at": time.time()}
    except Exception as e:  # noqa: BLE001 — a backup must never crash the caller
        return {"ok": False, "error": str(e)}


def _prune(dest_dir: Path) -> None:
    """Keep only the newest _KEEP dated bundles (never touch 'latest')."""
    dated = sorted(dest_dir.glob("vera-vault-20*.ctwin"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in dated[_KEEP:]:
        try:
            p.unlink()
        except OSError:
            pass


def status() -> str:
    d = backup_dir()
    copies = sorted(d.glob("vera-vault-20*.ctwin"), key=lambda p: p.stat().st_mtime, reverse=True)
    where = "iCloud Drive (off this Mac — survives it)" if is_offsite() else f"local folder ({d})"
    if not copies:
        return f"Backups → {where}. None yet — run `ctwin backup now` (or it runs after you add memories)."
    newest = copies[0]
    when = datetime.fromtimestamp(newest.stat().st_mtime).strftime("%b %d, %Y %-I:%M %p")
    return (f"Backups → {where}.\n  {len(copies)} kept · newest {newest.name} ({when}).\n"
            f"  Restore key: run `ctwin backup key` and keep it safe (needed to restore on a new Mac).")


def maybe_run_after_capture() -> None:
    """Called right after a memory/keepsake is added — fire a backup, quietly. Debounced
    so a burst of adds doesn't write a pile of bundles."""
    marker = vault._memory_dir() / ".last_backup"
    try:
        last = marker.stat().st_mtime
    except OSError:
        last = 0
    if time.time() - last < 120:   # at most one auto-backup per 2 min
        return
    run()
    try:
        marker.write_text(str(time.time()))
    except OSError:
        pass
