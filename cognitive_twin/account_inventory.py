"""
account_inventory — the accounts you have, and which ones are dead weight.

Ankur asked for this directly: read through the inbox and keep track of *useless
vs unused vs mostly-used* accounts. Signing up for services leaves a trail in your
mail — welcome emails, receipts, security alerts, newsletters. This reads that
trail (from the local, sealed ``mail_store`` index — no re-fetch) and tells you,
per service:

  • mostly-used  — recent + regular contact; a service you're actively in.
  • unused       — you have an account but it's gone quiet for a long time
                   (a candidate to close / a subscription to cancel).
  • useless      — high-volume marketing you never asked to keep; the classic
                   "unsubscribe" pile.
  • dormant-signup — one welcome/verify email and basically nothing since:
                   an account you made and forgot.

Everything runs on the sealed on-device index; nothing leaves the machine. These
are *heuristics over your mail*, so they're labelled as suggestions, not verdicts
— Vera never closes or unsubscribes anything on its own ([[feedback_user_action_only]]).

CLI:
    python3 -m cognitive_twin.account_inventory report [--months 6]
    python3 -m cognitive_twin.account_inventory unused   [--months 12]
    python3 -m cognitive_twin.account_inventory useless

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from . import mail_store


# ── what counts as an "account" signal ─────────────────────────────────────────
# Subjects/senders that mark a real service relationship (vs a person emailing).
_ACCOUNT_HINTS = re.compile(
    r"\b(welcome|verify|confirm your|account|sign[- ]?in|log[- ]?in|password|"
    r"receipt|invoice|order|subscription|security alert|two[- ]?factor|"
    r"your\s+\w+\s+(account|order|receipt)|activate)\b",
    re.IGNORECASE,
)
_MARKETING_HINTS = re.compile(
    r"\b(sale|% off|deal|offer|newsletter|unsubscribe|promo|save|discount|"
    r"new arrivals|last chance|limited time)\b",
    re.IGNORECASE,
)
# Personal-mail domains — we don't treat these as "services/accounts".
_PERSONAL_DOMAINS = {
    "gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com",
    "me.com", "proton.me", "protonmail.com", "live.com", "aol.com",
}

_NOW = lambda: datetime.now(timezone.utc)
_DAY = 86400.0


@dataclass
class Account:
    service: str                  # the display name / domain
    domain: str
    total: int = 0
    marketing: int = 0
    account_signals: int = 0
    first_ts: float | None = None
    last_ts: float | None = None
    unsub_seen: bool = False
    label: str = ""               # mostly-used | unused | useless | dormant-signup | active
    reason: str = ""
    sample_subjects: list[str] = field(default_factory=list)

    def days_since_last(self) -> float | None:
        if self.last_ts is None:
            return None
        return (_NOW().timestamp() - self.last_ts) / _DAY

    def span_days(self) -> float | None:
        if self.first_ts is None or self.last_ts is None:
            return None
        return max(0.0, (self.last_ts - self.first_ts) / _DAY)


# ── build the inventory from the sealed mail index ─────────────────────────────
def _service_name(domain: str, sample_name: str) -> str:
    # Prefer the org part of the domain (github.com → github), fall back to name.
    core = domain.split(".")
    if len(core) >= 2:
        return core[-2]
    return sample_name or domain


def build(*, unused_months: int = 6) -> list[Account]:
    """Group the local mail index by service domain and classify each account.
    ``unused_months`` = how long of silence marks an account 'unused'."""
    metas = mail_store.read_all()
    by_domain: dict[str, Account] = {}
    names: dict[str, str] = defaultdict(str)

    for m in metas:
        dom = m.domain()
        if not dom or dom in _PERSONAL_DOMAINS:
            continue  # people, not services
        acc = by_domain.get(dom)
        if acc is None:
            acc = Account(service=_service_name(dom, m.from_name), domain=dom)
            by_domain[dom] = acc
        acc.total += 1
        if m.from_name and not names[dom]:
            names[dom] = m.from_name
        text = f"{m.subject} {m.from_name}"
        if _MARKETING_HINTS.search(text):
            acc.marketing += 1
        if _ACCOUNT_HINTS.search(text):
            acc.account_signals += 1
        if m.unsubscribe:
            acc.unsub_seen = True
        if m.ts:
            acc.first_ts = m.ts if acc.first_ts is None else min(acc.first_ts, m.ts)
            acc.last_ts = m.ts if acc.last_ts is None else max(acc.last_ts, m.ts)
        if len(acc.sample_subjects) < 3 and m.subject:
            acc.sample_subjects.append(m.subject[:70])

    unused_days = unused_months * 30.0
    for acc in by_domain.values():
        if names[acc.domain]:
            acc.service = _service_name(acc.domain, names[acc.domain])
        _classify(acc, unused_days)
    # order: most actionable first (useless + unused), then by volume
    order = {"useless": 0, "unused": 1, "dormant-signup": 2, "active": 3, "mostly-used": 4}
    return sorted(by_domain.values(), key=lambda a: (order.get(a.label, 9), -a.total))


def _classify(acc: Account, unused_days: float) -> None:
    days = acc.days_since_last()
    marketing_ratio = acc.marketing / acc.total if acc.total else 0.0

    # Useless: high-volume marketing you can unsubscribe from, regardless of age.
    if acc.total >= 4 and marketing_ratio >= 0.6 and acc.account_signals == 0:
        acc.label = "useless"
        acc.reason = (f"{acc.total} msgs, ~{marketing_ratio:.0%} marketing, no account "
                      f"activity — unsubscribe candidate.")
        return

    # Dormant signup: basically one account email and then silence.
    if acc.total <= 2 and acc.account_signals >= 1 and (days or 0) > unused_days:
        acc.label = "dormant-signup"
        acc.reason = (f"signed up ~{_ago(acc.first_ts)}, ~{int(days)}d since last mail "
                      f"— an account you made and forgot.")
        return

    # Unused: a real service, but quiet for a long time.
    if days is not None and days > unused_days:
        acc.label = "unused"
        acc.reason = (f"last contact {int(days)}d ago ({acc.total} msgs total) "
                      f"— dormant; consider closing / cancelling.")
        return

    # Mostly-used: recent + repeated, real account activity.
    if acc.total >= 5 and (days is not None and days <= 30) and acc.account_signals >= 1:
        acc.label = "mostly-used"
        acc.reason = f"{acc.total} msgs, active in the last 30d — a service you use."
        return

    acc.label = "active"
    acc.reason = f"{acc.total} msg(s), last {int(days)}d ago." if days is not None else \
                 f"{acc.total} msg(s)."


def _ago(ts: float | None) -> str:
    if not ts:
        return "unknown"
    days = (_NOW().timestamp() - ts) / _DAY
    if days < 60:
        return f"{int(days)}d ago"
    if days < 730:
        return f"{int(days / 30)}mo ago"
    return f"{days / 365:.1f}y ago"


# ── human report ───────────────────────────────────────────────────────────────
_ICON = {"useless": "🗑", "unused": "💤", "dormant-signup": "👻",
         "mostly-used": "★", "active": "·"}


def report(*, unused_months: int = 6) -> str:
    if mail_store.count() == 0:
        return ("No mail indexed yet. Run `python3 -m cognitive_twin.mail_store sync` "
                "first (needs IMAP configured).")
    accounts = build(unused_months=unused_months)
    if not accounts:
        return "No service accounts found in the indexed mail."

    buckets: dict[str, list[Account]] = defaultdict(list)
    for a in accounts:
        buckets[a.label].append(a)

    lines = [f"Account inventory — {len(accounts)} services across your inbox:"]
    counts = {k: len(v) for k, v in buckets.items()}
    lines.append("  " + " · ".join(f"{v} {k}" for k, v in counts.items()))
    lines.append("")
    for label in ("useless", "unused", "dormant-signup", "mostly-used", "active"):
        for a in buckets.get(label, []):
            lines.append(f"  {_ICON.get(label,'·')} [{label:<14}] {a.service} ({a.domain})")
            lines.append(f"       {a.reason}")
    return "\n".join(lines)


def suggestions(unused_months: int = 6) -> dict[str, list[str]]:
    """Machine-readable: {'unsubscribe': [...], 'close_or_cancel': [...]}."""
    accounts = build(unused_months=unused_months)
    return {
        "unsubscribe": [a.domain for a in accounts if a.label == "useless"],
        "close_or_cancel": [a.domain for a in accounts if a.label in ("unused", "dormant-signup")],
        "mostly_used": [a.domain for a in accounts if a.label == "mostly-used"],
    }


# ── CLI ─────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "report"
    args = argv[1:]
    months = int(args[args.index("--months") + 1]) if "--months" in args else 6

    if cmd == "report":
        print(report(unused_months=months)); return 0
    if cmd == "unused":
        accs = [a for a in build(unused_months=months) if a.label in ("unused", "dormant-signup")]
        if not accs:
            print("No clearly-unused accounts found."); return 0
        print("Unused / dormant accounts (candidates to close):")
        for a in accs:
            print(f"  💤 {a.service} ({a.domain}) — {a.reason}")
        return 0
    if cmd == "useless":
        accs = [a for a in build(unused_months=months) if a.label == "useless"]
        if not accs:
            print("No high-volume marketing accounts found."); return 0
        print("Useless (unsubscribe candidates):")
        for a in accs:
            print(f"  🗑 {a.service} ({a.domain}) — {a.reason}")
        return 0
    print("usage: python3 -m cognitive_twin.account_inventory [report|unused|useless] [--months N]")
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
