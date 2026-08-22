"""
Security tests for the local viz/Brain HTTP surface.

The viz server is a segment too — it must be safe on its own: bind localhost
only, and never let a GET (or a cross-site POST) mutate state (CSRF). These
guard against re-opening that hole.
"""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from cognitive_twin import security, viz


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("CTWIN_MEMORY_DIR", str(tmp_path))
    srv = viz.make_server(port=7898)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)
    yield "http://127.0.0.1:7898"
    srv.shutdown()


def _req(base, path, method="GET", origin=None):
    r = urllib.request.Request(base + path, method=method)
    if origin:
        r.add_header("Origin", origin)
    try:
        resp = urllib.request.urlopen(r, timeout=5)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_get_cannot_mutate_the_dial(server):
    # a GET to /api/tone/set (the classic <img src> CSRF) must be refused
    code, _ = _req(server, "/api/tone/set?bluntness=1")
    assert code == 405


def test_cross_site_post_is_refused(server):
    code, body = _req(server, "/api/tone/set?bluntness=1", "POST", "http://evil.example")
    assert code == 403
    assert "cross-site" in body.get("error", "").lower()


def test_same_origin_post_works(server):
    code, body = _req(server, "/api/tone/set?bluntness=0.5", "POST", server)
    assert code == 200
    assert body.get("bluntness") == 0.5


def test_reads_stay_on_get(server):
    # non-mutating reads are fine on GET
    assert _req(server, "/api/tone")[0] == 200
    assert _req(server, "/api/feel?q=hello")[0] == 200


def test_server_binds_localhost_only():
    # never expose the twin off-machine
    assert viz.HOST == "127.0.0.1"


def test_doctor_audits_the_http_surface():
    ok, label, _detail = security._check_local_http()
    assert ok
    assert label == "Local HTTP surface"
