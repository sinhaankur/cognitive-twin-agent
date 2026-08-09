"""
secrets_store — your credentials in the macOS Keychain, not a plaintext .env.

The weak link we found: IMAP_PASSWORD and the OAuth client secret sat unencrypted
in a ``.env`` file. This module moves them into the **macOS Keychain**, which the
OS encrypts and binds to your login. Code asks for a secret by name; the value
never lives on disk in plaintext.

Lookup order (first hit wins), so it's safe to adopt gradually:
  1. macOS Keychain  — the secure home. Set with ``set``/``put`` below.
  2. Environment      — legacy ``.env`` still works as a fallback.
On macOS, ``get(name, prefer_env=False)`` will *migrate* a value it finds only in
the environment into the Keychain, so secrets drift toward the secure store over
time. Nothing is ever written to disk by this module.

Off macOS (no ``security`` binary) it degrades to the environment, honestly — it
does not pretend to secure a secret it can't.

CLI:
    python3 -m cognitive_twin.secrets_store set IMAP_PASSWORD      # prompts, hidden input
    python3 -m cognitive_twin.secrets_store get IMAP_PASSWORD       # prints (for scripts)
    python3 -m cognitive_twin.secrets_store has IMAP_PASSWORD       # exit 0 if present
    python3 -m cognitive_twin.secrets_store list                    # names only, never values
    python3 -m cognitive_twin.secrets_store rm  IMAP_PASSWORD
    python3 -m cognitive_twin.secrets_store migrate                 # move known .env secrets → Keychain

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import getpass
import os
import subprocess
import sys

# One Keychain "service" namespace for all of Vera's secrets. Each secret is a
# separate generic-password item keyed by its NAME (account), so they're managed
# individually in Keychain Access.app too.
_SERVICE = "cognitive-twin-secrets"

# The secrets Vera knows how to manage — the audit/doctor/migrate surface. Add a
# new credential name here when a feature needs one.
KNOWN_SECRETS = [
    "IMAP_PASSWORD",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "GOOGLE_OAUTH_CLIENT_ID",     # not secret, but convenient to co-locate
    "NOTIFY_WEBHOOK",
    "AGENT_DAEMON_TOKEN",
]


def _has_keychain() -> bool:
    return sys.platform == "darwin" and _which("security") is not None


def _which(cmd: str) -> str | None:
    from shutil import which
    return which(cmd)


# ── Keychain primitives (mirror vault.py's approach, per-named-secret) ─────────
def _kc_read(name: str) -> str | None:
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-s", _SERVICE, "-a", name, "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            # -w prints the password with a trailing newline; strip only that.
            return r.stdout.rstrip("\n")
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _kc_write(name: str, value: str) -> bool:
    try:
        # -U updates if it already exists. -a account = the secret's NAME.
        # (No -T: we let the `security` tool read it back like vault.py does;
        # an empty trusted-app list makes the item unreadable without a GUI prompt.)
        r = subprocess.run(
            ["security", "add-generic-password", "-a", name, "-s", _SERVICE,
             "-w", value, "-U"],
            capture_output=True, timeout=5,
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _kc_delete(name: str) -> bool:
    try:
        r = subprocess.run(
            ["security", "delete-generic-password", "-s", _SERVICE, "-a", name],
            capture_output=True, timeout=5,
        )
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


# ── public API ────────────────────────────────────────────────────────────────
def put(name: str, value: str) -> bool:
    """Store a secret in the Keychain. Returns False (and warns) if there's no
    Keychain — we don't silently 'store' a secret we can't secure."""
    if not value:
        raise ValueError("refusing to store an empty secret")
    if not _has_keychain():
        return False
    return _kc_write(name, value)


def get(name: str, *, prefer_env: bool = False, migrate: bool = True) -> str | None:
    """Fetch a secret. Keychain first (secure), then environment (legacy .env).
    If it's only in the environment and a Keychain exists, migrate it in so the
    plaintext copy stops being the source of truth."""
    env_val = os.environ.get(name)
    if prefer_env and env_val:
        return env_val

    kc_val = _kc_read(name) if _has_keychain() else None
    if kc_val is not None:
        return kc_val

    if env_val:
        if migrate and _has_keychain():
            _kc_write(name, env_val)  # best-effort; env stays as-is for this run
        return env_val
    return None


def has(name: str) -> bool:
    return get(name, migrate=False) is not None


def in_keychain(name: str) -> bool:
    return _has_keychain() and _kc_read(name) is not None


def in_env_plaintext(name: str) -> bool:
    """True if the secret is currently exposed via the environment (i.e. a .env
    plaintext value) — what the doctor flags as a risk."""
    return bool(os.environ.get(name))


def delete(name: str) -> bool:
    return _kc_delete(name) if _has_keychain() else False


def migrate_known() -> dict[str, str]:
    """Move any KNOWN_SECRETS present in the environment into the Keychain.
    Returns {name: outcome}. Does not (can't) edit your .env file — it just makes
    the Keychain the authoritative source; remove the .env lines afterwards."""
    out: dict[str, str] = {}
    if not _has_keychain():
        return {n: "no-keychain" for n in KNOWN_SECRETS if os.environ.get(n)}
    for name in KNOWN_SECRETS:
        val = os.environ.get(name)
        if not val:
            continue
        if _kc_read(name) is not None:
            out[name] = "already-in-keychain"
            continue
        out[name] = "migrated" if _kc_write(name, val) else "failed"
    return out


def audit() -> list[tuple[str, str]]:
    """Per-secret at-rest state for the doctor: keychain / env-plaintext / absent."""
    rows: list[tuple[str, str]] = []
    for name in KNOWN_SECRETS:
        if in_keychain(name):
            state = "keychain"
            if in_env_plaintext(name):
                state += " + also in env (remove the .env line)"
        elif in_env_plaintext(name):
            state = "ENV PLAINTEXT (move to Keychain)"
        else:
            state = "absent"
        rows.append((name, state))
    return rows


# ── CLI ─────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    if not argv:
        print("usage: python3 -m cognitive_twin.secrets_store "
              "[set|get|has|rm|list|migrate|audit] [NAME]")
        return 2
    cmd = argv[0]
    name = argv[1] if len(argv) > 1 else None

    if cmd in ("set", "put"):
        if not name:
            print("usage: set NAME"); return 2
        if not _has_keychain():
            print("✗ No macOS Keychain here — can't securely store secrets on this "
                  "platform. Keep using environment variables."); return 1
        value = getpass.getpass(f"Value for {name} (hidden): ")
        print("✓ stored in Keychain." if put(name, value) else "✗ failed to store.");
        return 0 if has(name) else 1
    if cmd == "get":
        if not name:
            print("usage: get NAME"); return 2
        val = get(name)
        if val is None:
            print("", end=""); return 1
        print(val); return 0
    if cmd == "has":
        if not name:
            print("usage: has NAME"); return 2
        return 0 if has(name) else 1
    if cmd in ("rm", "delete"):
        if not name:
            print("usage: rm NAME"); return 2
        print("✓ removed." if delete(name) else "nothing to remove / no keychain.")
        return 0
    if cmd == "list":
        print("Known secrets (names only):")
        for n, state in audit():
            print(f"  {n:<28} {state}")
        return 0
    if cmd == "migrate":
        res = migrate_known()
        if not res:
            print("Nothing in the environment to migrate."); return 0
        for n, outcome in res.items():
            print(f"  {n:<28} {outcome}")
        print("\nNow delete those lines from your .env so the Keychain is the only "
              "copy.")
        return 0
    if cmd == "audit":
        for n, state in audit():
            print(f"  {n:<28} {state}")
        return 0
    print(f"unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
