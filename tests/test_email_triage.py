"""
Email triage tests — pure unit tests on the rule layer. No IMAP and no LLM: the
classifier is a function of the message headers/subject, so we build messages in
memory and assert the verdict. The LLM tie-breaker is only reached when the rules
return None, which we also assert (without calling a model).

Run: python -m pytest tests/ -q   (or: python tests/test_email_triage.py)
"""

from __future__ import annotations

import email
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cognitive_twin.email_triage import (  # noqa: E402
    DEFAULT_ALLOW, GOOD, MARKETING, SPAM,
    classify_by_rules, render_report,
)


def _msg(raw: str):
    return email.message_from_string(raw)


ALLOW = set(DEFAULT_ALLOW)


def test_newsletter_is_marketing():
    v = classify_by_rules(_msg(
        "From: Deals <news@shop.example.com>\n"
        "Subject: 50% off sale ends tonight\n"
        "List-Unsubscribe: <mailto:u@shop.example.com>\n"
        "List-Id: Shop News <news.shop.example.com>\n"
        "Precedence: bulk\n\nBody"), ALLOW)
    assert v is not None and v.label == MARKETING
    assert "List-Unsubscribe" in v.signals


def test_personal_note_is_good():
    v = classify_by_rules(_msg(
        "From: Priya <priya@gmail.com>\n"
        "Subject: lunch on Thursday?\n\nAre you free?"), ALLOW)
    assert v is not None and v.label == GOOD


def test_transactional_receipt_is_good():
    v = classify_by_rules(_msg(
        "From: receipts@stripe.com\n"
        "Subject: Your receipt from Acme\n\nPaid $12."), ALLOW)
    assert v is not None and v.label == GOOD


def test_authfail_bulk_is_spam():
    v = classify_by_rules(_msg(
        "From: Prince <prince@sketchy.tld>\n"
        "Subject: You won a prize claim now\n"
        "List-Unsubscribe: <mailto:x@sketchy.tld>\n"
        "Authentication-Results: mx; spf=fail; dkim=fail\n\nSend details."), ALLOW)
    assert v is not None and v.label == SPAM
    assert "auth-fail" in v.signals


def test_allowlisted_sender_is_good():
    allow = ALLOW | {"boss@work.example.com"}
    v = classify_by_rules(_msg(
        "From: The Boss <boss@work.example.com>\n"
        "Subject: newsletter sale unsubscribe promo\n"  # promo words, still trusted
        "List-Unsubscribe: <mailto:x@work.example.com>\n\nHi"), allow)
    assert v is not None and v.label == GOOD
    assert "allowlist" in v.signals


def test_single_bulk_signal_plain_subject_defers_to_llm():
    # One bulk header, no promo words → genuinely ambiguous → rules return None.
    v = classify_by_rules(_msg(
        "From: updates@service.example.com\n"
        "Subject: your account summary\n"
        "List-Unsubscribe: <mailto:x@service.example.com>\n\nHi"), ALLOW)
    assert v is None  # handed to the LLM tie-breaker


def test_single_bulk_signal_with_promo_subject_is_marketing():
    v = classify_by_rules(_msg(
        "From: updates@service.example.com\n"
        "Subject: Limited time offer just for you\n"
        "List-Unsubscribe: <mailto:x@service.example.com>\n\nHi"), ALLOW)
    assert v is not None and v.label == MARKETING
    assert "promo subject" in v.signals


def test_report_is_read_only_language_and_counts():
    v = classify_by_rules(_msg(
        "From: a@b.com\nSubject: hi\n\nyo"), ALLOW)
    report = render_report([v])
    assert "read-only" in report
    assert "nothing in your mailbox was touched" in report
    assert "1 good" in report


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
