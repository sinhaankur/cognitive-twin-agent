"""
iCloud sync transport — Vera stays the same companion across devices, privately.

The bundle is sealed BEFORE it touches iCloud; pull is a MERGE not an overwrite;
per-device keys never move; and with no iCloud container every call is a clean
no-op. Here we point the container at a temp folder to simulate two devices
sharing one private iCloud Drive.
"""
from __future__ import annotations

import importlib
import tempfile
from pathlib import Path

from cognitive_twin import sync_icloud


def test_no_icloud_is_a_clean_noop(monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())
    monkeypatch.setattr(sync_icloud, "container_dir", lambda: None)
    assert sync_icloud.available() is False
    assert "local" in sync_icloud.push().lower()
    assert "local" in sync_icloud.pull().lower()
    assert "off" in sync_icloud.status().lower()


def test_push_writes_a_sealed_bundle(monkeypatch, tmp_path):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())
    monkeypatch.setattr(sync_icloud, "container_dir", lambda: tmp_path)
    monkeypatch.setattr(sync_icloud, "device_name", lambda: "MacA")
    sync_icloud.set_passphrase("shared-secret-123")
    from cognitive_twin import memory
    memory.record("a memory to carry", "noted")
    out = sync_icloud.push()
    assert "Pushed" in out
    bundle = tmp_path / "MacA.ctwin"
    assert bundle.exists()
    raw = bundle.read_bytes()
    assert b"a memory to carry" not in raw        # sealed, not plaintext


def test_push_needs_a_passphrase(monkeypatch, tmp_path):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())
    monkeypatch.setattr(sync_icloud, "container_dir", lambda: tmp_path)
    monkeypatch.setattr(sync_icloud, "device_name", lambda: "MacA")
    monkeypatch.delenv("CTWIN_SYNC_PASSPHRASE", raising=False)
    assert "passphrase" in sync_icloud.push().lower()


def test_two_devices_merge_without_loss(monkeypatch, tmp_path):
    # device A pushes a unique memory
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())
    monkeypatch.setattr(sync_icloud, "container_dir", lambda: tmp_path)
    monkeypatch.setattr(sync_icloud, "device_name", lambda: "MacA")
    from cognitive_twin import security, memory
    importlib.reload(security); importlib.reload(memory)
    sync_icloud.set_passphrase("shared-secret-123")
    memory.record("DEVICE A unique Munnar trip", "noted")
    assert "Pushed" in sync_icloud.push()

    # device B (fresh) with the SAME passphrase pulls → A's memory merges in
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())
    importlib.reload(security); importlib.reload(memory)
    monkeypatch.setattr(sync_icloud, "device_name", lambda: "iPhoneB")
    sync_icloud.set_passphrase("shared-secret-123")
    assert memory.entries() == []                 # B starts empty
    out = sync_icloud.pull()
    assert "Merged 1" in out
    importlib.reload(memory)
    texts = [(e.get("prompt") or e.get("text") or "") for e in memory.entries()]
    assert any("Munnar" in t for t in texts)      # A's memory is now on B


def test_pull_ignores_own_bundle(monkeypatch, tmp_path):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", tempfile.mkdtemp())
    monkeypatch.setattr(sync_icloud, "container_dir", lambda: tmp_path)
    monkeypatch.setattr(sync_icloud, "device_name", lambda: "MacA")
    sync_icloud.set_passphrase("shared-secret-123")
    sync_icloud.push()                            # writes MacA.ctwin
    # pulling sees only our own bundle → nothing to merge
    assert "Nothing" in sync_icloud.pull() or "nothing" in sync_icloud.pull().lower()
