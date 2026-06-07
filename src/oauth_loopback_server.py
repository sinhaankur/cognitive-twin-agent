from __future__ import annotations

import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    shared: dict[str, Any] = {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        params = urllib.parse.parse_qs(parsed.query)
        _OAuthCallbackHandler.shared["code"] = (params.get("code") or [""])[0]
        _OAuthCallbackHandler.shared["state"] = (params.get("state") or [""])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<html><body><h2>Authorization captured.</h2><p>Return to terminal.</p></body></html>")

    def log_message(self, format, *args):
        return


def wait_for_oauth_callback(host: str = "127.0.0.1", port: int = 8765, timeout_seconds: int = 180) -> dict[str, str]:
    _OAuthCallbackHandler.shared = {}
    httpd = HTTPServer((host, port), _OAuthCallbackHandler)
    httpd.timeout = 1

    def _serve():
        while "code" not in _OAuthCallbackHandler.shared:
            httpd.handle_request()

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)
    httpd.server_close()

    code = str(_OAuthCallbackHandler.shared.get("code", ""))
    state = str(_OAuthCallbackHandler.shared.get("state", ""))
    return {"code": code, "state": state}
