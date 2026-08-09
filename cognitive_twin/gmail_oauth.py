"""
gmail_oauth — Google OAuth 2.0 for Vera's Gmail access, on YOUR computer only.

This is the single cloud touchpoint in an otherwise zero-cloud app, and it is a
narrow one: OAuth lets Vera read/send *your* mail through *your* Google account.
The tokens it obtains are sealed at rest with the same device-bound key Vera uses
for her memory (``vault.py`` — ChaCha20-Poly1305, key in the macOS Keychain bound
to this Mac + this account). Copy the token file to another machine and it reads
as noise. Nothing about your mail is ever sent anywhere except back to Google to
fetch it; no third-party server, no telemetry.

Threat model, honestly: OAuth means Google (your provider) still serves your mail
over the network — that is unavoidable for *any* email client. What we guarantee
is that everything Vera *derives* (the local index, summaries, drafts) stays on
this device, encrypted, and that reasoning runs on your on-device LLM.

Flow (installed-app / loopback, no client secret exposure risk on a personal Mac):
  1. Open Google's consent screen in your browser.
  2. Google redirects to http://127.0.0.1:<port>/callback with a one-time code.
  3. We exchange the code for access + refresh tokens, then seal them.
  4. Later calls silently refresh the access token from the stored refresh token.

Setup (one time) — see docs; you create an OAuth *Desktop app* client in a Google
Cloud project and put its id/secret in the environment:
    GOOGLE_OAUTH_CLIENT_ID      the OAuth client id
    GOOGLE_OAUTH_CLIENT_SECRET  the OAuth client secret
    GOOGLE_OAUTH_REDIRECT_URI   default http://127.0.0.1:8765/callback

CLI:
    python3 -m cognitive_twin.gmail_oauth login    # run the consent flow once
    python3 -m cognitive_twin.gmail_oauth status    # show token state (no secrets)
    python3 -m cognitive_twin.gmail_oauth logout    # delete the stored tokens

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import base64
import http.server
import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any

# Scopes: read all mail + send. Kept explicit so it's obvious what Vera can do.
# gmail.readonly = read any message; gmail.send = send as you. No delete/modify.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://mail.google.com/",  # needed for IMAP/SMTP XOAUTH2
]

_AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URI = "https://oauth2.googleapis.com/token"


class GmailAuthError(RuntimeError):
    """Anything that stops us getting a usable access token."""


# ── where tokens live (sealed, this device only) ──────────────────────────────
def _home() -> Path:
    root = Path(os.environ.get("CTWIN_HOME", Path.home() / ".cognitive-twin"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _token_path() -> Path:
    return _home() / "gmail_token.sealed"


def _client() -> tuple[str, str, str]:
    # Client id/secret from the Keychain first (secure), env as legacy fallback.
    from .secrets_store import get as _secret
    cid = (_secret("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    secret = (_secret("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    redirect = os.environ.get(
        "GOOGLE_OAUTH_REDIRECT_URI", "http://127.0.0.1:8765/callback"
    ).strip()
    if not cid or not secret:
        raise GmailAuthError(
            "Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET (a Google "
            "Cloud OAuth *Desktop app* client) in your environment first. Nothing "
            "leaves this Mac except the OAuth exchange with Google."
        )
    return cid, secret, redirect


def _save_tokens(tok: dict[str, Any]) -> None:
    """Seal the token bundle at rest with Vera's device-bound key."""
    from . import vault

    blob = vault.seal_bytes(json.dumps(tok).encode("utf-8"))
    path = _token_path()
    path.write_bytes(blob)
    try:
        os.chmod(path, 0o600)  # owner-only, belt and braces
    except OSError:
        pass


def _load_tokens() -> dict[str, Any] | None:
    path = _token_path()
    if not path.is_file():
        return None
    from . import vault

    data = path.read_bytes()
    try:
        raw = vault.open_bytes(data) if vault.is_sealed_bytes(data) else data
        return json.loads(raw)
    except Exception as e:  # corrupt / wrong-device key → treat as no token
        raise GmailAuthError(f"stored Gmail token unreadable on this device: {e}")


# ── the loopback consent flow ─────────────────────────────────────────────────
class _CodeCatcher(http.server.BaseHTTPRequestHandler):
    """A tiny one-shot server that captures the ?code=… redirect and shows a
    'you can close this tab' page. Never touches the network itself."""

    code: str | None = None
    state_expected: str | None = None
    error: str | None = None

    def do_GET(self):  # noqa: N802 (stdlib naming)
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.rstrip("/") not in ("/callback", ""):
            self.send_response(404)
            self.end_headers()
            return
        qs = urllib.parse.parse_qs(parsed.query)
        if qs.get("state", [None])[0] != _CodeCatcher.state_expected:
            _CodeCatcher.error = "state mismatch (possible CSRF) — aborted."
        elif "error" in qs:
            _CodeCatcher.error = qs["error"][0]
        else:
            _CodeCatcher.code = qs.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        msg = ("Vera is connected to your Gmail. You can close this tab."
               if _CodeCatcher.code else
               f"Sign-in failed: {_CodeCatcher.error}. You can close this tab.")
        self.wfile.write(
            f"<html><body style='font:16px system-ui;padding:3rem'>"
            f"<h2>{'✓' if _CodeCatcher.code else '✗'} {msg}</h2>"
            f"</body></html>".encode("utf-8")
        )

    def log_message(self, *_):  # silence the default stderr logging
        pass


def login(*, open_browser: bool = True, timeout_s: int = 300) -> dict[str, Any]:
    """Run the consent flow once and store sealed tokens. Returns token metadata
    (no secrets). Safe to re-run; it overwrites the stored tokens."""
    import requests

    cid, secret, redirect = _client()
    parsed = urllib.parse.urlparse(redirect)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8765

    state = secrets.token_urlsafe(24)
    _CodeCatcher.code = None
    _CodeCatcher.error = None
    _CodeCatcher.state_expected = state

    params = {
        "client_id": cid,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",       # we want a refresh token
        "prompt": "consent",            # force a refresh token even on re-login
        "state": state,
    }
    auth_url = _AUTH_URI + "?" + urllib.parse.urlencode(params)

    server = http.server.HTTPServer((host, port), _CodeCatcher)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        if open_browser:
            webbrowser.open(auth_url)
        else:
            print("Open this URL to authorize Vera:\n", auth_url)
        deadline = time.time() + timeout_s
        while _CodeCatcher.code is None and _CodeCatcher.error is None:
            if time.time() > deadline:
                raise GmailAuthError("timed out waiting for Google sign-in.")
            time.sleep(0.2)
    finally:
        server.shutdown()

    if _CodeCatcher.error:
        raise GmailAuthError(f"authorization failed: {_CodeCatcher.error}")

    resp = requests.post(_TOKEN_URI, data={
        "code": _CodeCatcher.code,
        "client_id": cid,
        "client_secret": secret,
        "redirect_uri": redirect,
        "grant_type": "authorization_code",
    }, timeout=30)
    if resp.status_code != 200:
        raise GmailAuthError(f"token exchange failed: {resp.status_code} {resp.text[:200]}")
    tok = resp.json()
    tok["obtained_at"] = int(time.time())
    if "refresh_token" not in tok:
        # Google only returns a refresh token on first consent; keep any prior one.
        prior = _load_tokens() or {}
        if prior.get("refresh_token"):
            tok["refresh_token"] = prior["refresh_token"]
    _save_tokens(tok)
    return _redact(tok)


def _refresh(tok: dict[str, Any]) -> dict[str, Any]:
    import requests

    cid, secret, _ = _client()
    refresh_token = tok.get("refresh_token")
    if not refresh_token:
        raise GmailAuthError("no refresh token stored — run `login` again.")
    resp = requests.post(_TOKEN_URI, data={
        "client_id": cid,
        "client_secret": secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }, timeout=30)
    if resp.status_code != 200:
        raise GmailAuthError(f"token refresh failed: {resp.status_code} {resp.text[:200]}")
    fresh = resp.json()
    tok["access_token"] = fresh["access_token"]
    tok["expires_in"] = fresh.get("expires_in", 3600)
    tok["obtained_at"] = int(time.time())
    _save_tokens(tok)
    return tok


def access_token() -> str:
    """A valid access token, refreshing silently if the stored one is stale.
    Raises GmailAuthError if Vera isn't connected yet (caller should say so)."""
    tok = _load_tokens()
    if not tok:
        raise GmailAuthError("Gmail isn't connected yet — run "
                             "`python3 -m cognitive_twin.gmail_oauth login`.")
    age = int(time.time()) - int(tok.get("obtained_at", 0))
    if not tok.get("access_token") or age >= int(tok.get("expires_in", 3600)) - 60:
        tok = _refresh(tok)
    return tok["access_token"]


def xoauth2_string(user: str, token: str | None = None) -> str:
    """The base64 SASL XOAUTH2 initial-response IMAP/SMTP want."""
    token = token or access_token()
    raw = f"user={user}\x01auth=Bearer {token}\x01\x01"
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


def is_connected() -> bool:
    try:
        return _load_tokens() is not None
    except GmailAuthError:
        return False


def logout() -> bool:
    path = _token_path()
    if path.is_file():
        path.unlink()
        return True
    return False


def _redact(tok: dict[str, Any]) -> dict[str, Any]:
    """Token metadata safe to print / return (no access/refresh secrets)."""
    return {
        "connected": True,
        "scope": tok.get("scope", " ".join(SCOPES)),
        "has_refresh_token": bool(tok.get("refresh_token")),
        "obtained_at": tok.get("obtained_at"),
        "expires_in": tok.get("expires_in"),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────
def _main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "status"
    if cmd == "login":
        try:
            meta = login()
        except GmailAuthError as e:
            print(f"✗ {e}")
            return 1
        print("✓ Vera is connected to your Gmail (tokens sealed to this Mac).")
        print("  scope:", meta["scope"])
        return 0
    if cmd == "status":
        if not is_connected():
            print("Gmail: not connected. Run `python3 -m cognitive_twin.gmail_oauth login`.")
            return 0
        try:
            print("Gmail: connected ✓", json.dumps(_redact(_load_tokens())))
        except GmailAuthError as e:
            print(f"Gmail: token present but unreadable on this device — {e}")
        return 0
    if cmd == "logout":
        print("✓ removed stored Gmail tokens." if logout() else "Nothing to remove.")
        return 0
    print("usage: python3 -m cognitive_twin.gmail_oauth [login|status|logout]")
    return 2


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
