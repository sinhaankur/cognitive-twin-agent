"""
Email triage — read your inbox over IMAP and tell you which messages are real
and which are marketing/spam. Read-only: this module never deletes, moves, or
marks anything. It opens the mailbox in read-only mode and only reports.

How it decides (rules first, twin on the fence):
  1. Cheap, transparent rules run on every message — the ``List-Unsubscribe``
     header, bulk/precedence headers, an allowlist of senders you trust, and a
     few marketing keyword/domain signals. Most bulk mail is caught here.
  2. Only the genuinely ambiguous messages are handed to the local twin (the
     same OpenAI-compatible client the rest of Vera uses) for a verdict. That
     keeps it fast and mostly offline; the model is a tie-breaker, not the
     workhorse.

Everything stays on your machine: IMAP talks to your provider directly and the
LLM points at a local server. Nothing is uploaded anywhere else.

CLI:
    python3 -m cognitive_twin.email_triage report [--limit 50] [--folder INBOX]

Config (env, same style as the rest of the app):
    IMAP_HOST      e.g. imap.gmail.com / imap.fastmail.com / imap.mail.me.com
    IMAP_PORT      default 993 (SSL)
    IMAP_USER      your email address
    IMAP_PASSWORD  an app-specific password (never your main login)
    IMAP_FOLDER    default INBOX
    # LLM tie-breaker reuses LLM_BASE_URL / LLM_MODEL / LLM_API_KEY.
"""

from __future__ import annotations

import email
import email.utils
import imaplib
import os
import re
from dataclasses import dataclass, field
from email.header import decode_header, make_header
from email.message import Message
from typing import Any

# ---- verdict vocabulary ------------------------------------------------------
GOOD = "good"           # a real, person-to-you or transactional message
MARKETING = "marketing"  # newsletters, promos, bulk campaigns
SPAM = "spam"           # unsolicited / deceptive
UNSURE = "unsure"       # rules couldn't decide and no LLM was available

# Senders you always trust. Domains and exact addresses both work. Kept small
# and obvious on purpose; the point is to short-circuit false positives on the
# people/services that clearly matter.
DEFAULT_ALLOW = {
    # transactional senders people rarely want filed as marketing
    "no-reply@accounts.google.com",
}

# Words that, in a *subject*, lean promotional. Deliberately conservative — the
# structured headers below are far more reliable than keyword-spotting.
_PROMO_WORDS = re.compile(
    r"\b(sale|% off|discount|coupon|deal|offer|newsletter|unsubscribe|"
    r"limited time|act now|buy now|free shipping|webinar|promo|"
    r"black friday|cyber monday)\b",
    re.IGNORECASE,
)


@dataclass
class Verdict:
    uid: str
    sender: str
    subject: str
    label: str                     # GOOD | MARKETING | SPAM | UNSURE
    reason: str                    # human-readable "why"
    by: str = "rules"              # "rules" | "llm"
    signals: list[str] = field(default_factory=list)


# ---- header helpers ----------------------------------------------------------
def _decode(value: str | None) -> str:
    """Decode RFC 2047 encoded-words (e.g. ``=?UTF-8?…?=``) to plain text."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _sender_addr(msg: Message) -> str:
    _, addr = email.utils.parseaddr(msg.get("From", ""))
    return addr.lower()


def _domain(addr: str) -> str:
    return addr.rsplit("@", 1)[-1] if "@" in addr else ""


# ---- rule layer --------------------------------------------------------------
def classify_by_rules(msg: Message, allow: set[str]) -> Verdict | None:
    """Return a Verdict if the rules are confident, else ``None`` (hand off to
    the LLM). Signals are collected so the report can explain the call."""
    sender = _sender_addr(msg)
    subject = _decode(msg.get("Subject"))
    domain = _domain(sender)
    signals: list[str] = []

    # 1. Trusted sender → good, no argument.
    if sender in allow or domain in allow:
        return Verdict("", sender, subject, GOOD,
                       f"{sender or domain} is on your allowlist", signals=["allowlist"])

    # 2. Structured bulk-mail headers. These are set by senders who blast
    #    campaigns and are the single most reliable marketing signal.
    has_unsub = bool(msg.get("List-Unsubscribe"))
    has_list_id = bool(msg.get("List-Id"))
    precedence = (msg.get("Precedence") or "").strip().lower()
    is_bulk = precedence in {"bulk", "list", "junk"}
    feedback_id = bool(msg.get("Feedback-ID") or msg.get("X-CSA-Complaints"))
    campaign = bool(msg.get("X-Campaign") or msg.get("X-Mailer", "").lower().startswith(
        ("mailchimp", "sendgrid", "amazonses", "sparkpost", "constant contact")))

    if has_unsub:
        signals.append("List-Unsubscribe")
    if has_list_id:
        signals.append("List-Id")
    if is_bulk:
        signals.append(f"Precedence: {precedence}")
    if feedback_id:
        signals.append("Feedback-ID")
    if campaign:
        signals.append("bulk-sender headers")

    # Two or more independent bulk signals → confidently marketing.
    if len(signals) >= 2:
        return Verdict("", sender, subject, MARKETING,
                       "carries bulk-mail headers (" + ", ".join(signals) + ")",
                       signals=signals)

    # 3. Spam-ish authentication failure. Only flag when combined with bulk
    #    traits, to avoid punishing a legit sender with a misconfigured relay.
    auth = (msg.get("Authentication-Results") or "").lower()
    auth_fail = ("spf=fail" in auth or "dkim=fail" in auth or "dmarc=fail" in auth)
    if auth_fail and (has_unsub or is_bulk):
        return Verdict("", sender, subject, SPAM,
                       "failed sender authentication and looks like bulk mail",
                       signals=signals + ["auth-fail"])

    # A single bulk signal + promo-flavoured subject → still clearly marketing.
    if signals and _PROMO_WORDS.search(subject):
        signals.append("promo subject")
        return Verdict("", sender, subject, MARKETING,
                       "a bulk signal plus a promotional subject", signals=signals)

    # No bulk headers and a plain subject → very likely a real message.
    if not signals and not _PROMO_WORDS.search(subject):
        return Verdict("", sender, subject, GOOD,
                       "no bulk-mail headers; reads like a personal/transactional message",
                       signals=["clean headers"])

    # Otherwise: genuinely on the fence — let the twin decide.
    return None


# ---- LLM tie-breaker ---------------------------------------------------------
def classify_by_llm(msg: Message, snippet: str) -> Verdict | None:
    """Ask the local twin for a verdict on an ambiguous message. Returns None if
    no local LLM is reachable (caller then records the message as UNSURE)."""
    try:
        from .llm.openai_client import OpenAIClient, OpenAIError
        from .llm.ollama_client import ChatMessage
    except Exception:
        return None

    client = OpenAIClient(
        model=os.environ.get("LLM_MODEL", "local-model"),
        host=os.environ.get("LLM_BASE_URL", "http://localhost:1234/v1"),
        api_key=os.environ.get("LLM_API_KEY", ""),
        temperature=0.0,
    )
    if not client.is_up():
        return None

    sender = _sender_addr(msg)
    subject = _decode(msg.get("Subject"))
    prompt = (
        "Classify this email as exactly one of: good, marketing, spam.\n"
        "- good: a real personal or transactional message meant for this recipient.\n"
        "- marketing: newsletters, promotions, or bulk campaigns.\n"
        "- spam: unsolicited or deceptive mail.\n"
        "Answer with the single word, then a dash and a short reason.\n\n"
        f"From: {sender}\nSubject: {subject}\n\n{snippet[:1200]}"
    )
    try:
        reply = client.chat([ChatMessage(role="user", content=prompt)])
    except OpenAIError:
        return None

    text = (reply.content or "").strip().lower()
    label = UNSURE
    for cand in (SPAM, MARKETING, GOOD):  # check spam/marketing before good
        if cand in text:
            label = cand
            break
    reason = reply.content.strip() if reply.content else "twin verdict"
    return Verdict("", sender, subject, label, reason, by="llm", signals=["llm"])


# ---- message body snippet ----------------------------------------------------
def _text_snippet(msg: Message) -> str:
    """Best-effort plain-text preview, for the LLM tie-breaker only."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", "replace")
                except Exception:
                    continue
        return ""
    try:
        payload = msg.get_payload(decode=True)
        if payload is None:
            return ""
        return payload.decode(msg.get_content_charset() or "utf-8", "replace")
    except Exception:
        return ""


# ---- IMAP fetch + triage -----------------------------------------------------
def triage(
    *,
    host: str,
    user: str,
    password: str,
    port: int = 993,
    folder: str = "INBOX",
    limit: int = 50,
    allow: set[str] | None = None,
    use_llm: bool = True,
) -> list[Verdict]:
    """Fetch the most recent ``limit`` messages read-only and classify each."""
    allow = (allow or set()) | DEFAULT_ALLOW
    verdicts: list[Verdict] = []

    conn = imaplib.IMAP4_SSL(host, port)
    try:
        conn.login(user, password)
        # readonly=True: the mailbox is never modified, and fetching does not
        # set the \Seen flag.
        conn.select(folder, readonly=True)
        typ, data = conn.search(None, "ALL")
        if typ != "OK":
            return verdicts
        uids = data[0].split()
        for uid in reversed(uids[-limit:]):  # newest first
            typ, msg_data = conn.fetch(uid, "(BODY.PEEK[])")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            v = classify_by_rules(msg, allow)
            if v is None:
                if use_llm:
                    v = classify_by_llm(msg, _text_snippet(msg))
                if v is None:
                    v = Verdict("", _sender_addr(msg), _decode(msg.get("Subject")),
                                UNSURE, "rules undecided; no local twin reachable")
            v.uid = uid.decode() if isinstance(uid, bytes) else str(uid)
            verdicts.append(v)
    finally:
        try:
            conn.logout()
        except Exception:
            pass
    return verdicts


# ---- report ------------------------------------------------------------------
_ICON = {GOOD: "✓", MARKETING: "▤", SPAM: "✗", UNSURE: "?"}


def render_report(verdicts: list[Verdict]) -> str:
    counts: dict[str, int] = {GOOD: 0, MARKETING: 0, SPAM: 0, UNSURE: 0}
    lines: list[str] = []
    for v in verdicts:
        counts[v.label] = counts.get(v.label, 0) + 1
        subj = (v.subject[:60] + "…") if len(v.subject) > 61 else v.subject
        tag = "twin" if v.by == "llm" else "rule"
        lines.append(f"  {_ICON.get(v.label, '?')} [{v.label:<9} · {tag}] {v.sender}")
        lines.append(f"      {subj or '(no subject)'}")
        lines.append(f"      → {v.reason}")
    header = (
        f"Triaged {len(verdicts)} message(s) — read-only, nothing in your "
        f"mailbox was touched.\n"
        f"  {counts[GOOD]} good · {counts[MARKETING]} marketing · "
        f"{counts[SPAM]} spam · {counts[UNSURE]} unsure\n"
    )
    return header + "\n".join(lines)


# ---- CLI ---------------------------------------------------------------------
def _main(argv: list[str]) -> int:
    if not argv or argv[0] != "report":
        print("usage: python3 -m cognitive_twin.email_triage report "
              "[--limit N] [--folder INBOX] [--no-llm]")
        return 2

    limit = 50
    folder = os.environ.get("IMAP_FOLDER", "INBOX")
    use_llm = True
    args = argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1]); i += 2
        elif args[i] == "--folder" and i + 1 < len(args):
            folder = args[i + 1]; i += 2
        elif args[i] == "--no-llm":
            use_llm = False; i += 1
        else:
            i += 1

    host = os.environ.get("IMAP_HOST")
    user = os.environ.get("IMAP_USER")
    password = os.environ.get("IMAP_PASSWORD")
    if not (host and user and password):
        print("✗ Set IMAP_HOST, IMAP_USER and IMAP_PASSWORD (an app-specific "
              "password) in your environment first. Nothing is uploaded; IMAP "
              "talks to your provider directly.")
        return 1

    port = int(os.environ.get("IMAP_PORT", "993"))
    try:
        verdicts = triage(host=host, user=user, password=password, port=port,
                          folder=folder, limit=limit, use_llm=use_llm)
    except imaplib.IMAP4.error as e:
        print(f"✗ IMAP error: {e}\n  (Check the host/credentials; use an "
              f"app-specific password, not your main login.)")
        return 1

    print(render_report(verdicts))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
