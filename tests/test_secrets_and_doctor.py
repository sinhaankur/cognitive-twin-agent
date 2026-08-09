"""
Secrets store + security doctor tests.

The secrets tests avoid your real Keychain: they force the no-keychain path and
assert the environment fallback + audit behave (the Keychain round-trip itself is
verified interactively on macOS, not in CI where no Keychain exists). The doctor
tests assert it flags problems and passes a clean setup, in a temp memory dir.

Run: python -m pytest tests/test_secrets_and_doctor.py -q
     (or: python tests/test_secrets_and_doctor.py)
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fresh(tmp: Path):
    os.environ["CTWIN_MEMORY_DIR"] = str(tmp)
    from cognitive_twin import vault, security, secrets_store
    importlib.reload(vault)
    importlib.reload(security)
    importlib.reload(secrets_store)
    vault._key_cache = None
    return security, secrets_store


def test_env_fallback_when_no_keychain(tmp_path, monkeypatch):
    _, S = _fresh(tmp_path)
    monkeypatch.setattr(S, "_has_keychain", lambda: False)
    monkeypatch.setenv("SOME_TOKEN", "abc123")
    assert S.get("SOME_TOKEN") == "abc123"          # falls back to env
    assert S.has("SOME_TOKEN") is True
    assert S.get("MISSING") is None


def test_put_refuses_without_keychain(tmp_path, monkeypatch):
    _, S = _fresh(tmp_path)
    monkeypatch.setattr(S, "_has_keychain", lambda: False)
    # Won't silently 'store' a secret it can't secure.
    assert S.put("X", "y") is False


def test_put_rejects_empty(tmp_path):
    _, S = _fresh(tmp_path)
    try:
        S.put("X", "")
    except ValueError:
        return
    assert False, "expected ValueError on empty secret"


def test_audit_flags_env_plaintext(tmp_path, monkeypatch):
    _, S = _fresh(tmp_path)
    monkeypatch.setattr(S, "_has_keychain", lambda: False)
    monkeypatch.setenv("IMAP_PASSWORD", "hunter2")
    states = dict(S.audit())
    assert "ENV PLAINTEXT" in states["IMAP_PASSWORD"]


def test_doctor_passes_clean_setup(tmp_path, monkeypatch):
    S, secrets = _fresh(tmp_path)
    # No personal stores, no plaintext env secrets → doctor should be happy on the
    # fronts it can check here. Clear any inherited secret envs.
    for n in secrets.KNOWN_SECRETS:
        monkeypatch.delenv(n, raising=False)
    safe, checks = S.doctor()
    labels = {label: (ok, detail) for ok, label, detail in checks}
    assert labels["Data sealed at rest"][0] is True
    assert labels["Secrets in Keychain"][0] is True
    assert labels["Network egress"][0] is True  # egress scan finds only known-good


def test_doctor_flags_plaintext_secret(tmp_path, monkeypatch):
    S, secrets = _fresh(tmp_path)
    monkeypatch.setattr(secrets, "_has_keychain", lambda: False)
    monkeypatch.setenv("IMAP_PASSWORD", "leaky")
    safe, checks = S.doctor()
    secret_check = next(c for c in checks if c[1] == "Secrets in Keychain")
    assert secret_check[0] is False
    assert safe is False


if __name__ == "__main__":
    import tempfile

    class _MP:
        """Minimal monkeypatch for standalone runs (no pytest)."""
        def __init__(self): self._env = {}; self._attr = []
        def setattr(self, obj, name, val):
            self._attr.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)
        def setenv(self, k, v): self._env[k] = os.environ.get(k); os.environ[k] = v
        def delenv(self, k, raising=True): self._env[k] = os.environ.pop(k, None)
        def undo(self):
            for obj, name, old in reversed(self._attr): setattr(obj, name, old)
            for k, old in self._env.items():
                if old is None: os.environ.pop(k, None)
                else: os.environ[k] = old

    import inspect
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            with tempfile.TemporaryDirectory() as d:
                mp = _MP()
                try:
                    params = inspect.signature(fn).parameters
                    args = [Path(d)] if "tmp_path" in params else []
                    if "monkeypatch" in params:
                        args.append(mp)
                    fn(*args)
                    print(f"  ✓ {name}")
                except AssertionError as e:
                    failures += 1
                    print(f"  ✗ {name}: {e}")
                finally:
                    mp.undo()
    print("OK" if not failures else f"{failures} FAILED")
    sys.exit(1 if failures else 0)
