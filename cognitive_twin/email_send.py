"""
email_send — let Vera send email as you, over your own Gmail. On-device auth.

Reading your inbox was half of email; this is the other half — sending. It uses
the SAME Gmail app password already in your Keychain (secrets_store), over SMTP
with SSL, straight to Google. No third-party mail service, no Vera server.

The safety model (deliberate, matches user-action-only):
  - Sending only happens when something explicitly calls send() — never on a
    timer, never as a side effect of reading. A draft is not a send.
  - Vera surfaces drafts (cover letters, replies) for YOU; a human step turns a
    draft into a send.
  - The booker + other automations can email you *your own address* to report
    outcomes (a notification), which is low-risk and opt-in.

Config (same as reading): IMAP_USER = your Gmail address (the From/login),
IMAP_PASSWORD in the Keychain. SMTP host defaults to smtp.gmail.com:465 (SSL).

CLI:
    python3 -m cognitive_twin.email_send test          # send yourself a test mail
    python3 -m cognitive_twin.email_send send --to a@b.com --subject "Hi" --body "..."

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any


class EmailSendError(RuntimeError):
    pass


def _config() -> tuple[str, str, str, int]:
    from .secrets_store import get as _secret
    user = os.environ.get("IMAP_USER", "")
    password = _secret("IMAP_PASSWORD") or ""
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    return user, password, host, port


def is_ready() -> bool:
    user, password, _, _ = _config()
    return bool(user and password)


def send(*, to: str | list[str], subject: str, body: str,
         from_addr: str | None = None, html: str | None = None) -> dict[str, Any]:
    """Send one email over your Gmail SMTP. Returns {ok, to} or raises
    EmailSendError. This is the ONLY path that sends — call it explicitly."""
    user, password, host, port = _config()
    if not (user and password):
        raise EmailSendError(
            "Email isn't configured to send. Set IMAP_USER and store IMAP_PASSWORD "
            "in the Keychain (`secrets_store set IMAP_PASSWORD`).")

    recipients = [to] if isinstance(to, str) else list(to)
    msg = EmailMessage()
    msg["From"] = from_addr or user
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")

    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
            s.login(user, password)
            s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise EmailSendError(
            "Gmail rejected the login. Use an app password (not your main "
            f"password) and 2-Step Verification. ({e.smtp_code})")
    except (smtplib.SMTPException, OSError) as e:
        raise EmailSendError(f"send failed: {e}")
    return {"ok": True, "to": recipients, "subject": subject}


def notify_self(subject: str, body: str) -> dict[str, Any]:
    """Email YOUR own address — the low-risk path automations use to report
    outcomes (booker result, daily briefing). No-op-safe if unconfigured."""
    user, password, _, _ = _config()
    if not (user and password):
        return {"ok": False, "note": "email not configured (no Keychain password)"}
    return send(to=user, subject=subject, body=body)


# ── CLI ─────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "test"
    args = argv[1:]

    def opt(flag, default=""):
        return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else default

    if cmd == "test":
        try:
            r = notify_self("Vera test email",
                            "This is a test from Vera's email_send. If you got this, "
                            "sending works.")
        except EmailSendError as e:
            print(f"✗ {e}"); return 1
        print(f"✓ sent a test to yourself ({r.get('to')})." if r.get("ok")
              else f"not sent: {r.get('note')}")
        return 0 if r.get("ok") else 1
    if cmd == "send":
        to = opt("--to")
        if not to:
            print("usage: send --to a@b.com --subject S --body B"); return 2
        try:
            send(to=to, subject=opt("--subject", "(no subject)"), body=opt("--body", ""))
        except EmailSendError as e:
            print(f"✗ {e}"); return 1
        print(f"✓ sent to {to}."); return 0
    print("usage: python3 -m cognitive_twin.email_send [test|send]")
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
