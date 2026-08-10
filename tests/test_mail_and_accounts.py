"""
Mail store + account inventory tests — no live IMAP.

We seed the sealed index directly (the same records a real sync would write) and
assert: the index is sealed at rest, search/top-senders work, and the account
classifier puts services in the right bucket (mostly-used / useless / unused /
dormant-signup) while ignoring personal senders. Runs in a temp memory dir.

Run: python -m pytest tests/test_mail_and_accounts.py -q
     (or: python tests/test_mail_and_accounts.py)
"""

from __future__ import annotations

import importlib
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_NOW = time.time()
_DAY = 86400.0


def _fresh(tmp: Path):
    os.environ["CTWIN_MEMORY_DIR"] = str(tmp)
    from cognitive_twin import vault, security, mail_store, account_inventory
    importlib.reload(vault)
    importlib.reload(security)
    importlib.reload(mail_store)
    importlib.reload(account_inventory)
    vault._key_cache = None
    return security, mail_store, account_inventory


def _seed(security, mail_store, records):
    for m in records:
        security.append_line(mail_store._index_path(), asdict(m))


def _meta(mail_store, uid, dom, name, subject, days_ago, unsub=False):
    return mail_store.MailMeta(
        uid=str(uid), folder="INBOX", from_addr=f"x@{dom}", from_name=name,
        subject=subject, date="", ts=_NOW - days_ago * _DAY, unsubscribe=unsub,
    )


def test_index_is_sealed_at_rest(tmp_path):
    S, M, _ = _fresh(tmp_path)
    _seed(S, M, [_meta(M, 1, "github.com", "GitHub", "Security alert", 1)])
    raw = M._index_path().read_bytes()
    assert b"github.com" not in raw          # sealed
    assert M.count() == 1


def test_search_and_top_senders(tmp_path):
    S, M, _ = _fresh(tmp_path)
    _seed(S, M, [
        _meta(M, 1, "github.com", "GitHub", "PR merged", 1),
        _meta(M, 2, "github.com", "GitHub", "Security alert", 2),
        _meta(M, 3, "stripe.com", "Stripe", "Receipt", 3),
    ])
    assert [m.subject for m in M.search("github")] == ["PR merged", "Security alert"]
    top = dict(M.top_senders())
    assert top["x@github.com"] == 2


def test_classifier_buckets(tmp_path):
    S, M, A = _fresh(tmp_path)
    seed = []
    for i, d in enumerate([1, 3, 5, 8, 12, 20]):
        seed.append(_meta(M, 100 + i, "github.com", "GitHub",
                          "Security alert: sign-in" if i % 2 else "PR merged", d))
    for i, d in enumerate([2, 4, 6, 9, 15]):
        seed.append(_meta(M, 200 + i, "shopdeals.com", "ShopDeals",
                          "50% off SALE last chance", d, unsub=True))
    seed.append(_meta(M, 300, "oldbank.com", "OldBank", "Account statement", 400))
    seed.append(_meta(M, 400, "randomapp.io", "RandomApp", "Verify your account", 500))
    seed.append(_meta(M, 500, "gmail.com", "Friend", "lunch?", 3))  # person → ignored
    _seed(S, M, seed)

    labels = {a.domain: a.label for a in A.build(unused_months=6)}
    assert "gmail.com" not in labels                       # personal sender ignored
    assert labels["github.com"] == "mostly-used"
    assert labels["shopdeals.com"] == "useless"
    assert labels["randomapp.io"] == "dormant-signup"
    assert labels["oldbank.com"] in ("unused", "dormant-signup")

    sug = A.suggestions(unused_months=6)
    assert "shopdeals.com" in sug["unsubscribe"]
    assert "github.com" in sug["mostly_used"]
    assert "randomapp.io" in sug["close_or_cancel"]


def test_report_handles_empty_index(tmp_path):
    S, M, A = _fresh(tmp_path)
    out = A.report()
    assert "No mail indexed" in out


if __name__ == "__main__":
    import tempfile

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            with tempfile.TemporaryDirectory() as d:
                try:
                    fn(Path(d))
                    print(f"  ✓ {name}")
                except AssertionError as e:
                    failures += 1
                    print(f"  ✗ {name}: {e}")
    print("OK" if not failures else f"{failures} FAILED")
    sys.exit(1 if failures else 0)
