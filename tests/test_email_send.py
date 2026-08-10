"""
email_send tests — the config + safety logic, no real SMTP.

We never open a socket here: we assert readiness reflects config, that send()
refuses when unconfigured, and that notify_self is a safe no-op without a
password. Real sending is verified interactively (`email_send test`) once a Gmail
app password is in the Keychain.

Run: python -m pytest tests/test_email_send.py -q  (or: python tests/test_email_send.py)
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _mod(monkeypatch, *, user="", password=""):
    from cognitive_twin import email_send, secrets_store
    importlib.reload(secrets_store)
    importlib.reload(email_send)
    monkeypatch.setenv("IMAP_USER", user)
    # force secrets_store.get to return our password (no Keychain in CI)
    monkeypatch.setattr(email_send, "_config",
                        lambda: (user, password, "smtp.gmail.com", 465))
    return email_send


def test_not_ready_without_password(monkeypatch):
    E = _mod(monkeypatch, user="me@gmail.com", password="")
    assert E.is_ready() is False


def test_ready_with_user_and_password(monkeypatch):
    E = _mod(monkeypatch, user="me@gmail.com", password="app-pass")
    assert E.is_ready() is True


def test_send_refuses_when_unconfigured(monkeypatch):
    E = _mod(monkeypatch, user="", password="")
    try:
        E.send(to="x@y.com", subject="s", body="b")
    except E.EmailSendError:
        return
    assert False, "expected EmailSendError when unconfigured"


def test_notify_self_is_safe_noop(monkeypatch):
    E = _mod(monkeypatch, user="me@gmail.com", password="")
    r = E.notify_self("subj", "body")
    assert r["ok"] is False and "not configured" in r["note"]


if __name__ == "__main__":
    class _MP:
        def __init__(self): self._a = []; self._e = {}
        def setattr(self, o, n, v): self._a.append((o, n, getattr(o, n, None))); setattr(o, n, v)
        def setenv(self, k, v):
            import os; self._e[k] = os.environ.get(k); os.environ[k] = v
        def undo(self):
            import os
            for o, n, ov in reversed(self._a):
                if ov is None:
                    try: delattr(o, n)
                    except Exception: pass
                else: setattr(o, n, ov)
            for k, ov in self._e.items():
                if ov is None: os.environ.pop(k, None)
                else: os.environ[k] = ov

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            mp = _MP()
            try:
                fn(mp); print(f"  ✓ {name}")
            except AssertionError as e:
                failures += 1; print(f"  ✗ {name}: {e}")
            finally:
                mp.undo()
    print("OK" if not failures else f"{failures} FAILED")
    sys.exit(1 if failures else 0)
