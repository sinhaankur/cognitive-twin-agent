"""
email_intel — Vera's email skills: know your inbox, know your accounts.

Wraps the on-device, sealed mail modules as agent skills so the twin (and voice)
can answer things like "which accounts should I close?" or "sync my email" without
the CLI. Everything runs on the local, kernel-sealed index; nothing leaves the Mac
beyond the IMAP fetch to *your* provider. Vera reports and suggests — it never
unsubscribes, closes, or sends on its own ([[feedback_user_action_only]]).

Importing this module registers the skills on the default registry.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

from .base import default_registry as R


@R.add(
    "sync_email",
    "Fetch new email metadata from your inbox into the local sealed index "
    "(headers only, read-only — never marks mail read). Run before asking about "
    "accounts or senders if the index is stale.",
    {"type": "object", "properties": {
        "limit": {"type": "integer", "description": "max new messages to pull (default 500)"},
    }},
)
def sync_email(limit: int = 500) -> str:
    from ..mail_store import sync, MailStoreError
    import imaplib
    try:
        r = sync(limit=limit)
    except (MailStoreError, imaplib.IMAP4.error) as e:
        return f"Couldn't sync email: {e}"
    return (f"Synced {r['folder']}: {r['new']} new message(s), "
            f"{r['total_indexed']} indexed (all sealed on this Mac).")


@R.add(
    "account_inventory",
    "Report the accounts/services in your inbox, grouped as mostly-used, unused, "
    "dormant-signup, or useless (marketing). Helps you spot accounts to close or "
    "unsubscribe from. Read-only; nothing is changed.",
    {"type": "object", "properties": {
        "months": {"type": "integer", "description": "months of silence that marks an account 'unused' (default 6)"},
    }},
)
def account_inventory(months: int = 6) -> str:
    from .. import account_inventory as A
    return A.report(unused_months=months)


@R.add(
    "unused_accounts",
    "List just the accounts you likely don't use anymore (dormant / long-silent) "
    "— candidates to close or cancel. Read-only.",
    {"type": "object", "properties": {
        "months": {"type": "integer", "description": "silence threshold in months (default 12)"},
    }},
)
def unused_accounts(months: int = 12) -> str:
    from .. import account_inventory as A
    accs = [a for a in A.build(unused_months=months)
            if a.label in ("unused", "dormant-signup")]
    if not accs:
        return "No clearly-unused accounts found in your indexed mail."
    lines = ["Accounts you probably don't use (candidates to close):"]
    for a in accs:
        lines.append(f"  • {a.service} ({a.domain}) — {a.reason}")
    return "\n".join(lines)


@R.add(
    "search_email",
    "Search your local sealed mail index by sender or subject (read-only, "
    "on-device). Returns the newest matching messages.",
    {"type": "object", "properties": {
        "query": {"type": "string", "description": "text to find in sender or subject"},
    }, "required": ["query"]},
)
def search_email(query: str) -> str:
    from ..mail_store import search, count
    if count() == 0:
        return "No mail indexed yet — run sync_email first."
    hits = search(query)
    if not hits:
        return f"No messages matching '{query}'."
    lines = [f"Messages matching '{query}':"]
    for m in hits:
        lines.append(f"  {m.date[:10]}  {m.from_addr}  —  {m.subject[:70]}")
    return "\n".join(lines)


@R.add(
    "triage_inbox",
    "Classify recent inbox messages as good / marketing / spam (read-only IMAP). "
    "A quick 'what's worth my attention' pass.",
    {"type": "object", "properties": {
        "limit": {"type": "integer", "description": "how many recent messages (default 40)"},
    }},
)
def triage_inbox(limit: int = 40) -> str:
    import os
    import imaplib
    from ..email_triage import triage, render_report
    from ..secrets_store import get as _secret

    host = os.environ.get("IMAP_HOST", "imap.gmail.com")
    user = os.environ.get("IMAP_USER")
    password = _secret("IMAP_PASSWORD")
    if not (host and user and password):
        return ("Email isn't configured. Set IMAP_HOST/IMAP_USER and store "
                "IMAP_PASSWORD in the Keychain (secrets_store set IMAP_PASSWORD).")
    try:
        verdicts = triage(host=host, user=user, password=password,
                          port=int(os.environ.get("IMAP_PORT", "993")),
                          folder=os.environ.get("IMAP_FOLDER", "INBOX"), limit=limit)
    except imaplib.IMAP4.error as e:
        return f"Couldn't reach your inbox: {e}"
    return render_report(verdicts)
