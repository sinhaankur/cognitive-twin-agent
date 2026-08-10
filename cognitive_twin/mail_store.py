"""
mail_store — a local, encrypted index of your inbox, so Vera knows your life.

Vera reads your mail once, keeps a compact **sealed** index on this device, and
reasons over it locally. The point (Ankur's): the twin feels generic until it
knows what's actually happening — who writes to you, which accounts you signed up
for, what you actually use. This is the on-device memory that makes that possible.

Privacy — inherited from the security kernel:
  - Every indexed message is a line SEALED via ``security.append_line``
    (ChaCha20, key in the macOS Keychain, bound to this Mac + account). The index
    reads as noise if copied off this machine.
  - We fetch **headers only** by default (From/Subject/Date/List-* etc.) with IMAP
    ``BODY.PEEK`` — the mailbox is opened read-only and nothing is ever marked
    read, moved, or deleted.
  - IMAP talks to *your* provider directly (Gmail). Nothing is uploaded anywhere
    else; the reasoning runs on your on-device LLM.

Incremental: each sync remembers the highest UID seen per folder (sealed state),
so re-running only pulls what's new — reading "all your emails" once, cheaply
after that.

CLI:
    python3 -m cognitive_twin.mail_store sync [--limit N] [--folder INBOX] [--all]
    python3 -m cognitive_twin.mail_store search "invoice"
    python3 -m cognitive_twin.mail_store senders            # top senders by volume
    python3 -m cognitive_twin.mail_store status
    python3 -m cognitive_twin.mail_store clear

Config: IMAP_HOST / IMAP_PORT / IMAP_USER (env), IMAP_PASSWORD (Keychain via
secrets_store). Defaults suit Gmail (imap.gmail.com:993).

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import email
import email.utils
import imaplib
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import Message
from typing import Any, Iterable

from . import security


# ── storage (sealed via the kernel) ────────────────────────────────────────────
INDEX = "mail.jsonl"          # one sealed line per message (metadata only)
STATE = "mail_state.json"     # highest UID seen per folder (sealed)


def _index_path():
    return security.path(INDEX)


def _state_path():
    return security.path(STATE)


# ── the record we keep per message (metadata, not bodies) ──────────────────────
@dataclass
class MailMeta:
    uid: str
    folder: str
    from_addr: str
    from_name: str
    subject: str
    date: str                     # ISO-8601 (UTC) if parseable, else raw
    ts: float | None = None       # epoch seconds, for recency math
    list_id: str = ""             # List-Id / List-Unsubscribe presence → bulk/service
    unsubscribe: bool = False
    mailer: str = ""              # X-Mailer / bulk-sender hint
    flags: dict[str, Any] = field(default_factory=dict)

    def domain(self) -> str:
        return self.from_addr.rsplit("@", 1)[-1].lower() if "@" in self.from_addr else ""


# ── header helpers ─────────────────────────────────────────────────────────────
def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _addr_name(msg: Message) -> tuple[str, str]:
    name, addr = email.utils.parseaddr(msg.get("From", ""))
    return addr.lower(), _decode(name)


def _date_iso(msg: Message) -> tuple[str, float | None]:
    raw = msg.get("Date", "")
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        if dt is None:
            return raw, None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat(), dt.timestamp()
    except Exception:
        return raw, None


def _meta_from_msg(uid: str, folder: str, msg: Message) -> MailMeta:
    addr, name = _addr_name(msg)
    date_iso, ts = _date_iso(msg)
    return MailMeta(
        uid=uid,
        folder=folder,
        from_addr=addr,
        from_name=name,
        subject=_decode(msg.get("Subject")),
        date=date_iso,
        ts=ts,
        list_id=_decode(msg.get("List-Id")) or "",
        unsubscribe=bool(msg.get("List-Unsubscribe")),
        mailer=(msg.get("X-Mailer") or msg.get("X-CSA-Complaints") or "")[:80],
    )


# ── IMAP fetch (headers only, read-only) ───────────────────────────────────────
def _imap_config() -> tuple[str, str, str, int, str]:
    from .secrets_store import get as _secret

    host = os.environ.get("IMAP_HOST", "imap.gmail.com")
    user = os.environ.get("IMAP_USER", "")
    password = _secret("IMAP_PASSWORD") or ""
    port = int(os.environ.get("IMAP_PORT", "993"))
    folder = os.environ.get("IMAP_FOLDER", "INBOX")
    return host, user, password, port, folder


class MailStoreError(RuntimeError):
    pass


def _fetch_headers(*, host, user, password, port, folder, limit, since_uid=0) -> list[MailMeta]:
    """Fetch header metadata for up to ``limit`` newest messages after ``since_uid``.
    Read-only, BODY.PEEK — never marks anything read."""
    if not (host and user and password):
        raise MailStoreError(
            "Email isn't configured. Set IMAP_HOST / IMAP_USER (env) and store "
            "IMAP_PASSWORD in the Keychain: "
            "`python3 -m cognitive_twin.secrets_store set IMAP_PASSWORD`."
        )
    out: list[MailMeta] = []
    conn = imaplib.IMAP4_SSL(host, port)
    try:
        conn.login(user, password)
        conn.select(folder, readonly=True)
        # Only headers we index — fast + minimal footprint.
        hdr = "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE LIST-ID LIST-UNSUBSCRIBE X-MAILER)])"
        typ, data = conn.search(None, "ALL")
        if typ != "OK":
            return out
        uids = [u.decode() if isinstance(u, bytes) else str(u) for u in data[0].split()]
        # newest first, stop at ones we've already indexed
        for uid in reversed(uids):
            if since_uid and int(uid) <= since_uid:
                break
            if len(out) >= limit:
                break
            typ, msg_data = conn.fetch(uid, hdr)
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            out.append(_meta_from_msg(uid, folder, msg))
    finally:
        try:
            conn.logout()
        except Exception:
            pass
    return out


# ── sync (incremental, sealed) ─────────────────────────────────────────────────
def sync(*, limit: int = 500, folder: str | None = None, full: bool = False) -> dict[str, Any]:
    """Pull new message metadata and append it to the sealed index. Incremental by
    default (only messages newer than the last UID we saw); ``full=True`` re-reads
    up to ``limit`` regardless. Returns a small summary."""
    host, user, password, port, cfg_folder = _imap_config()
    folder = folder or cfg_folder
    state = security.read_state(_state_path(), default={}) or {}
    since = 0 if full else int(state.get(folder, {}).get("max_uid", 0))

    metas = _fetch_headers(host=host, user=user, password=password, port=port,
                           folder=folder, limit=limit, since_uid=since)
    for m in metas:
        security.append_line(_index_path(), asdict(m))

    max_uid = max([int(m.uid) for m in metas] + [since])
    state.setdefault(folder, {})["max_uid"] = max_uid
    state[folder]["last_sync"] = datetime.now(timezone.utc).isoformat()
    security.write_state(_state_path(), state)
    return {"folder": folder, "new": len(metas), "max_uid": max_uid,
            "total_indexed": count()}


# ── read / query the local index ───────────────────────────────────────────────
def read_all() -> list[MailMeta]:
    out: list[MailMeta] = []
    for data in security.read_lines(_index_path()):
        try:
            out.append(MailMeta(**data))
        except Exception:
            continue
    return out


def count() -> int:
    return len(security.read_lines(_index_path()))


def search(query: str, limit: int = 30) -> list[MailMeta]:
    """Substring search over sender + subject in the local index (newest first)."""
    q = query.lower().strip()
    hits = [m for m in read_all()
            if q in m.from_addr.lower() or q in m.from_name.lower() or q in m.subject.lower()]
    hits.sort(key=lambda m: m.ts or 0, reverse=True)
    return hits[:limit]


def top_senders(limit: int = 20) -> list[tuple[str, int]]:
    from collections import Counter
    c: Counter[str] = Counter(m.from_addr for m in read_all() if m.from_addr)
    return c.most_common(limit)


def clear() -> None:
    _index_path().unlink(missing_ok=True)
    _state_path().unlink(missing_ok=True)


def status() -> str:
    state = security.read_state(_state_path(), default={}) or {}
    n = count()
    parts = [f"Mail index: {n} message(s) sealed on this Mac."]
    for folder, s in state.items():
        parts.append(f"  {folder}: up to UID {s.get('max_uid')}, last sync {s.get('last_sync', '—')}")
    if n == 0:
        parts.append("  (empty — run `mail_store sync` once email is configured.)")
    return "\n".join(parts)


# ── CLI ─────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    args = argv[1:]

    def _opt(name: str, default: str | None = None) -> str | None:
        return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default

    if cmd == "sync":
        limit = int(_opt("--limit", "500"))
        folder = _opt("--folder")
        full = "--all" in args
        try:
            r = sync(limit=limit, folder=folder, full=full)
        except (MailStoreError, imaplib.IMAP4.error) as e:
            print(f"✗ {e}")
            return 1
        print(f"✓ Synced {r['folder']}: +{r['new']} new, {r['total_indexed']} total "
              f"(all sealed on this Mac).")
        return 0
    if cmd == "search":
        if not args:
            print("usage: search <query>"); return 2
        for m in search(" ".join(a for a in args if not a.startswith("--"))):
            print(f"  {m.date[:10]}  {m.from_addr:<32}  {m.subject[:60]}")
        return 0
    if cmd == "senders":
        for addr, n in top_senders():
            print(f"  {n:>5}  {addr}")
        return 0
    if cmd == "status":
        print(status()); return 0
    if cmd == "clear":
        clear(); print("✓ Cleared the local mail index."); return 0
    print("usage: python3 -m cognitive_twin.mail_store [sync|search|senders|status|clear]")
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
