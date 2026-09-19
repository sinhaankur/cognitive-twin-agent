"""WatchTower link: off by default, local-only, best-effort, never crashes."""

from __future__ import annotations

import os

from cognitive_twin import watchtower as wt


def _clear_env():
    for k in ("CTWIN_WATCHTOWER", "CTWIN_WATCHTOWER_BASE"):
        os.environ.pop(k, None)


def test_off_by_default():
    _clear_env()
    assert wt.is_enabled({}) is False
    # emitting while off is a silent no-op (returns False, sends nothing)
    assert wt.emit("reply", model="x", backend="local") is False
    assert wt.health({})["status"] == "off"


def test_enabled_by_env_or_config():
    _clear_env()
    assert wt.is_enabled({"watchtower": {"enabled": True}}) is True
    os.environ["CTWIN_WATCHTOWER"] = "1"
    try:
        assert wt.is_enabled({}) is True
    finally:
        _clear_env()


def test_base_url_is_loopback_by_default():
    _clear_env()
    assert wt.base_url({}).startswith("http://127.0.0.1")
    os.environ["CTWIN_WATCHTOWER_BASE"] = "http://127.0.0.1:9999/"
    try:
        assert wt.base_url({}) == "http://127.0.0.1:9999"  # trailing slash trimmed
    finally:
        _clear_env()


def test_unreachable_never_raises():
    _clear_env()
    os.environ["CTWIN_WATCHTOWER"] = "1"
    os.environ["CTWIN_WATCHTOWER_BASE"] = "http://127.0.0.1:1"  # nothing listens
    try:
        # both the emit and the health read must degrade quietly, not throw
        assert wt.emit("reply", model="unhosted/qwen2.5:14b", backend="unhosted") is False
        assert wt.health({})["status"] == "unreachable"
        assert "WatchTower" in wt.summarize_health({})
    finally:
        _clear_env()
