"""adblock safety: off by default, refuses local container control, confirm-gates
mutations, and never builds a shell string. Mirrors the control/watchtower posture."""

from __future__ import annotations

import os

from cognitive_twin import adblock


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("CTWIN_ADBLOCK", raising=False)
    assert adblock.is_enabled() is False
    # every entry point is inert when off
    assert "off" in adblock.status().lower()
    assert "off" in adblock.set_protection(True).lower()
    assert "off" in adblock.container("restart").lower()


def test_enabled_via_env(monkeypatch):
    monkeypatch.setenv("CTWIN_ADBLOCK", "1")
    assert adblock.is_enabled() is True
    monkeypatch.setenv("CTWIN_ADBLOCK", "0")
    assert adblock.is_enabled() is False


def test_refuses_local_container_control(monkeypatch):
    """The core of Ankur's rule: never control a DNS container on THIS machine."""
    monkeypatch.setenv("CTWIN_ADBLOCK", "1")
    adblock.set_confirm(lambda _a: True)          # even if the user confirms
    for host in ("", "localhost", "127.0.0.1", "0.0.0.0", "::1"):
        monkeypatch.setenv("CTWIN_ADBLOCK_HOST", host)
        out = adblock.container("stop").lower()
        assert "refus" in out or "this machine" in out


def test_container_confirm_gate(monkeypatch):
    monkeypatch.setenv("CTWIN_ADBLOCK", "1")
    monkeypatch.setenv("CTWIN_ADBLOCK_HOST", "10.88.111.50")   # a real box
    adblock.set_confirm(lambda _a: False)         # user denies
    out = adblock.container("restart").lower()
    assert "cancel" in out


def test_unknown_op_rejected(monkeypatch):
    monkeypatch.setenv("CTWIN_ADBLOCK", "1")
    monkeypatch.setenv("CTWIN_ADBLOCK_HOST", "10.88.111.50")
    out = adblock.container("rm -rf /").lower()    # not in the closed op set
    assert "unknown op" in out


def test_protection_confirm_gate(monkeypatch):
    monkeypatch.setenv("CTWIN_ADBLOCK", "1")
    adblock.set_confirm(lambda _a: False)
    out = adblock.set_protection(False).lower()
    assert "cancel" in out


def test_setup_hint_is_for_the_box_not_here():
    hint = adblock.setup_hint()
    assert "NOT this laptop" in hint
    assert "docker run" in hint
    # it is a printed instruction, never executed — no side effects to assert,
    # but confirm it names the router step so the user gets whole-home coverage.
    assert "router" in hint.lower()
