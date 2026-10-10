"""
sync_icloud — keep Vera the same companion across your devices, through YOUR
iCloud account, safely and privately.

The hard part (merging two devices' memory without losing either side) already
lives in sync.py. This is the TRANSPORT: it writes Vera's sealed bundle into your
private iCloud Drive container and reads the other device's bundle from there, so
Mac and iPhone stay in step automatically — no server of ours, nothing public.

Why this is safe + private (Ankur: "everything linked to iCloud account so safe
and private"):
  - The bundle is ALREADY sealed before it touches iCloud — it's exported through
    vault.export_bundle under a passphrase (ChaCha20-Poly1305). iCloud only ever
    holds ciphertext; Apple can't read it, and neither can anyone else.
  - It lives in iCloud Drive scoped to YOUR Apple ID. The trust is your iCloud
    account: the same person Apple already authenticates on both devices. Vera
    doesn't invent its own login — it inherits that trust.
  - PER-DEVICE KEYS NEVER MOVE. The bundle carries memory, not the device's
    sealing key (sync.merge_bundle refuses key material). Each device keeps its
    own Keychain key; the passphrase is what unlocks the shared bundle.
  - Pull is a MERGE, never an overwrite — both devices' edits survive, newest wins
    on a true conflict (see sync.py).

Flow per device, on a timer or on demand:
    push()  → export a fresh sealed bundle → drop it in iCloud as <device>.ctwin
    pull()  → for every OTHER device's bundle in iCloud → merge it in

No iCloud container present (not signed in, entitlement missing) → every call is a
clean no-op; Vera simply stays local. Offline is a valid state.

CLI:
    python3 -m cognitive_twin.sync_icloud status
    python3 -m cognitive_twin.sync_icloud push
    python3 -m cognitive_twin.sync_icloud pull
    python3 -m cognitive_twin.sync_icloud sync      # pull then push
"""

from __future__ import annotations

import os
import socket
import sys
import time
from pathlib import Path
from typing import Any

from . import security, sync, vault

# the app's iCloud ubiquity container, surfaced on the Mac as a normal folder.
# (The iOS app writes to the SAME container via its iCloud entitlement.)
_CONTAINER = "iCloud.com.sinhaankur.vera"
_SUBDIR = "sync"                      # bundles live here, one per device
_SUFFIX = ".ctwin"                    # a sealed bundle
_PASSPHRASE_STORE = "icloud.pass"     # the shared bundle passphrase (sealed locally)
_STAMP = "icloud_sync.json"           # last push/pull times


# ── locating the private iCloud Drive container ───────────────────────────────
def container_dir() -> Path | None:
    """The app's iCloud Drive folder on THIS Mac, or None when iCloud isn't set up
    (not signed in / no entitlement granted yet). Created on first use when present."""
    base = Path.home() / "Library" / "Mobile Documents" / _CONTAINER.replace(".", "~", 1)
    # macOS names the container "iCloud~com~sinhaankur~vera"
    alt = Path.home() / "Library" / "Mobile Documents" / ("iCloud~" + _CONTAINER.split(".", 1)[1].replace(".", "~"))
    for cand in (alt, base):
        if cand.parent.is_dir():
            # the Mobile Documents root exists → iCloud Drive is on. Use/make ours.
            try:
                d = cand / "Documents" / _SUBDIR
                d.mkdir(parents=True, exist_ok=True)
                return d
            except OSError:
                continue
    return None


def available() -> bool:
    return container_dir() is not None


def device_name() -> str:
    """A stable, filesystem-safe name for THIS device, for its bundle filename."""
    try:
        name = socket.gethostname().split(".")[0]
    except Exception:
        name = "device"
    return "".join(c for c in name if c.isalnum() or c in "-_") or "device"


# ── the shared passphrase (sealed on each device; set once, same on both) ─────
def set_passphrase(passphrase: str) -> str:
    if len(passphrase) < 6:
        return "Passphrase must be at least 6 characters."
    security.write_state(security.path(_PASSPHRASE_STORE), {"p": passphrase})
    return "Sync passphrase set (sealed on this device). Set the SAME one on your other device."


def _passphrase() -> str | None:
    d = security.read_state(security.path(_PASSPHRASE_STORE), default={})
    p = d.get("p") if isinstance(d, dict) else None
    return p or os.environ.get("CTWIN_SYNC_PASSPHRASE") or None


def _stamp(update: dict[str, Any] | None = None) -> dict[str, Any]:
    cur = security.read_state(security.path(_STAMP), default={})
    cur = cur if isinstance(cur, dict) else {}
    if update:
        cur.update(update)
        security.write_state(security.path(_STAMP), cur)
    return cur


# ── push / pull ───────────────────────────────────────────────────────────────
def push() -> str:
    """Export a fresh sealed bundle of this device's memory into iCloud. No-op when
    iCloud isn't available or no passphrase is set."""
    if security.is_locked():
        return "Vera is locked — sync halted until you release the kill switch."
    d = container_dir()
    if d is None:
        return "iCloud isn't set up here — staying local (that's fine)."
    pw = _passphrase()
    if not pw:
        return "No sync passphrase yet — run: sync_icloud set <passphrase> (same on both devices)."
    dest = d / f"{device_name()}{_SUFFIX}"
    try:
        # write to a temp name then move, so another device never reads a half file
        tmp = d / f".{device_name()}.tmp"
        vault.export_bundle(tmp, pw)
        os.replace(tmp, dest)
        _stamp({"last_push": time.time()})
        return f"Pushed this device's memory to iCloud ({dest.name}, sealed)."
    except Exception as e:                       # noqa: BLE001
        return f"Couldn't push: {e}"


def pull(*, dry_run: bool = False) -> str:
    """Merge every OTHER device's bundle from iCloud into this one. Never overwrites
    — a real merge (newest wins on conflict). No-op when iCloud/passphrase absent."""
    if security.is_locked():
        return "Vera is locked — sync halted until you release the kill switch."
    d = container_dir()
    if d is None:
        return "iCloud isn't set up here — staying local (that's fine)."
    pw = _passphrase()
    if not pw:
        return "No sync passphrase yet — run: sync_icloud set <passphrase> (same on both devices)."
    mine = f"{device_name()}{_SUFFIX}"
    merged = 0
    notes: list[str] = []
    for f in sorted(d.glob(f"*{_SUFFIX}")):
        if f.name == mine:
            continue                             # don't merge our own bundle
        try:
            rep = sync.merge_bundle(f, pw, dry_run=dry_run)
            merged += 1
            notes.append(f"{f.stem}: {getattr(rep, 'summary', lambda: 'merged')() if callable(getattr(rep, 'summary', None)) else 'merged'}")
        except Exception as e:                   # noqa: BLE001
            notes.append(f"{f.stem}: skipped ({e})")
    if not dry_run:
        _stamp({"last_pull": time.time()})
    if merged == 0:
        return "No other device's bundle in iCloud yet — nothing to merge."
    head = "(dry-run) " if dry_run else ""
    return f"{head}Merged {merged} other device(s) from iCloud." + (
        "\n  " + "\n  ".join(notes) if notes else "")


def sync_now() -> str:
    """Pull the others, then push ours — the one call a timer/menu uses."""
    out = [pull(), push()]
    return "\n".join(o for o in out if o)


def status() -> str:
    d = container_dir()
    if d is None:
        return ("iCloud sync: off (not signed into iCloud / app entitlement not "
                "granted). Vera is fully working locally.")
    pw = "set" if _passphrase() else "NOT set (run: sync_icloud set <passphrase>)"
    st = _stamp()
    def _ago(k):
        t = st.get(k)
        return f"{int((time.time() - t) / 60)} min ago" if t else "never"
    others = [f.stem for f in d.glob(f"*{_SUFFIX}") if f.name != f"{device_name()}{_SUFFIX}"]
    return (f"iCloud sync: ready. device '{device_name()}', passphrase {pw}.\n"
            f"  last push {_ago('last_push')} · last pull {_ago('last_pull')}\n"
            f"  other devices seen: {', '.join(others) if others else 'none yet'}\n"
            f"  container: {d}")


def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        print(status()); return 0
    if cmd == "set":
        print(set_passphrase(argv[1] if len(argv) > 1 else "")); return 0
    if cmd == "push":
        print(push()); return 0
    if cmd == "pull":
        print(pull(dry_run="--dry-run" in argv)); return 0
    if cmd in ("sync", "now"):
        print(sync_now()); return 0
    print("usage: python3 -m cognitive_twin.sync_icloud [status|set <pass>|push|pull|sync]")
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
