"""
life + dashboard tests — the standalone (no-assistant) surface.

Asserts: life.snapshot covers every area with a uniform shape; the dashboard is a
real HTTP app that serves the page + life + controls and toggles over HTTP; and —
critically — importing the dashboard pulls in NONE of Vera's voice/agent/LLM
stack (it must stand alone).

Run: python -m pytest tests/test_life_dashboard.py -q
     (or: python tests/test_life_dashboard.py)
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fresh(tmp: Path):
    os.environ["CTWIN_MEMORY_DIR"] = str(tmp)
    from cognitive_twin import vault, security, life, dashboard
    importlib.reload(vault)
    importlib.reload(security)
    importlib.reload(life)
    importlib.reload(dashboard)
    vault._key_cache = None
    return life, dashboard


def test_life_snapshot_uniform(tmp_path):
    life, _ = _fresh(tmp_path)
    snap = life.snapshot()
    keys = {a["key"] for a in snap}
    assert {"places", "email", "social", "careers", "booker"} <= keys
    for a in snap:
        assert "title" in a and "on" in a and "headline" in a


def test_life_status_text(tmp_path):
    life, _ = _fresh(tmp_path)
    txt = life.status_text()
    assert "Where you go" in txt and "Job search" in txt


def test_dashboard_has_no_vera_stack(tmp_path):
    """The standalone app must not drag in the voice/agent/LLM modules.

    Measures what importing the dashboard ADDS, not the global sys.modules state —
    so an earlier test in the suite having imported the Vera stack can't make this
    fail. We purge the assistant modules, import the dashboard fresh, and assert it
    did not re-introduce any of them (that is the real 'stands alone' contract)."""
    def _vera_stack():
        return {m for m in sys.modules
                if m.startswith("cognitive_twin.voice")
                or m.startswith("cognitive_twin.agent")
                or m.startswith("cognitive_twin.llm")
                or m.startswith("cognitive_twin.brain")}

    # start from a clean slate: drop any assistant modules a prior test imported
    for m in _vera_stack():
        del sys.modules[m]

    _fresh(tmp_path)

    leaked = _vera_stack()
    assert not leaked, f"dashboard pulled in assistant modules: {sorted(leaked)}"


def test_dashboard_http(tmp_path):
    _, dashboard = _fresh(tmp_path)
    httpd = ThreadingHTTPServer((dashboard.HOST, 0), dashboard._Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.2)
    base = f"http://127.0.0.1:{port}"

    def g(p):
        return urllib.request.urlopen(base + p, timeout=5).read().decode()

    def post(p, o):
        req = urllib.request.Request(base + p, data=json.dumps(o).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        return urllib.request.urlopen(req, timeout=5).read().decode()

    try:
        assert "Your life" in g("/")
        assert len(json.loads(g("/api/life"))["areas"]) == 5
        assert len(json.loads(g("/api/controls"))["controls"]) >= 5
        r = json.loads(post("/api/controls/set", {"key": "places", "on": True}))
        assert r.get("on") is True
        json.loads(post("/api/controls/set", {"key": "places", "on": False}))
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    import tempfile

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            with tempfile.TemporaryDirectory() as d:
                try:
                    fn(Path(d)); print(f"  ✓ {name}")
                except AssertionError as e:
                    failures += 1; print(f"  ✗ {name}: {e}")
                except Exception as e:
                    failures += 1; print(f"  ✗ {name}: {type(e).__name__}: {e}")
    print("OK" if not failures else f"{failures} FAILED")
    sys.exit(1 if failures else 0)
