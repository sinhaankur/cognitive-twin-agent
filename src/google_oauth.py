from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import keyring
import requests

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


@dataclass
class GoogleTokenState:
    access_token: str
    refresh_token: str
    expires_at_utc: str


class GoogleOAuthManager:
    def __init__(self) -> None:
        self.service_name = "cognitive-twin-agent"
        self.pending_account = "google_oauth_pending"
        self.token_account = "google_calendar_oauth_tokens"

    def begin_auth(self) -> dict[str, str]:
        client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
        if not client_id:
            raise RuntimeError("GOOGLE_OAUTH_CLIENT_ID is required")

        redirect_uri = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "http://127.0.0.1:8765/callback")
        scope = "https://www.googleapis.com/auth/calendar.readonly"

        state = secrets.token_urlsafe(24)
        verifier = self._code_verifier()
        challenge = self._code_challenge(verifier)

        pending = {
            "state": state,
            "verifier": verifier,
            "redirect_uri": redirect_uri,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        keyring.set_password(self.service_name, self.pending_account, json.dumps(pending, ensure_ascii=True))

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        query = "&".join(f"{k}={requests.utils.quote(v, safe='')}" for k, v in params.items())
        return {"authorization_url": f"{GOOGLE_AUTH_URL}?{query}", "state": state}

    def exchange_code(self, code: str, state: str) -> None:
        client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
        client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            raise RuntimeError("GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET are required")

        pending = self._load_pending()
        if state != pending.get("state"):
            raise RuntimeError("OAuth state mismatch")

        redirect_uri = str(pending.get("redirect_uri", ""))
        verifier = str(pending.get("verifier", ""))

        payload = {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        }

        response = requests.post(GOOGLE_TOKEN_URL, data=payload, timeout=20)
        response.raise_for_status()
        data = response.json()

        access_token = str(data.get("access_token", ""))
        refresh_token = str(data.get("refresh_token", ""))
        expires_in = int(data.get("expires_in", 3600))
        if not access_token or not refresh_token:
            raise RuntimeError("OAuth token exchange did not return refresh/access token")

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(300, expires_in - 60))
        token_state = GoogleTokenState(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at_utc=expires_at.isoformat(),
        )
        self._save_tokens(token_state)

    def get_access_token(self) -> str | None:
        token_state = self._load_tokens()
        if token_state is None:
            return None

        expires_at = datetime.fromisoformat(token_state.expires_at_utc)
        now = datetime.now(timezone.utc)
        if expires_at > now + timedelta(seconds=30):
            return token_state.access_token

        return self._refresh(token_state)

    def status(self) -> dict[str, Any]:
        token_state = self._load_tokens()
        if token_state is None:
            return {"configured": False}
        return {
            "configured": True,
            "expires_at_utc": token_state.expires_at_utc,
        }

    def _refresh(self, token_state: GoogleTokenState) -> str | None:
        client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
        client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            return None

        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": token_state.refresh_token,
            "grant_type": "refresh_token",
        }

        response = requests.post(GOOGLE_TOKEN_URL, data=payload, timeout=20)
        if response.status_code >= 400:
            return None

        data = response.json()
        access_token = str(data.get("access_token", ""))
        if not access_token:
            return None

        expires_in = int(data.get("expires_in", 3600))
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=max(300, expires_in - 60))
        updated = GoogleTokenState(
            access_token=access_token,
            refresh_token=token_state.refresh_token,
            expires_at_utc=expires_at.isoformat(),
        )
        self._save_tokens(updated)
        return access_token

    def _code_verifier(self) -> str:
        return base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode("ascii")

    def _code_challenge(self, verifier: str) -> str:
        digest = hashlib.sha256(verifier.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    def _load_pending(self) -> dict[str, Any]:
        raw = keyring.get_password(self.service_name, self.pending_account)
        if not raw:
            raise RuntimeError("No pending OAuth flow found. Run begin auth first.")
        return json.loads(raw)

    def _save_tokens(self, token_state: GoogleTokenState) -> None:
        keyring.set_password(
            self.service_name,
            self.token_account,
            json.dumps(
                {
                    "access_token": token_state.access_token,
                    "refresh_token": token_state.refresh_token,
                    "expires_at_utc": token_state.expires_at_utc,
                },
                ensure_ascii=True,
            ),
        )

    def _load_tokens(self) -> GoogleTokenState | None:
        raw = keyring.get_password(self.service_name, self.token_account)
        if not raw:
            return None
        payload = json.loads(raw)
        return GoogleTokenState(
            access_token=str(payload.get("access_token", "")),
            refresh_token=str(payload.get("refresh_token", "")),
            expires_at_utc=str(payload.get("expires_at_utc", "")),
        )
