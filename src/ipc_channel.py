from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import socket
from pathlib import Path
from typing import Any, Callable

import keyring


class SignedLocalIPC:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.socket_path = workspace_root / "memory" / "runtime" / "daemon.sock"
        self.service_name = "cognitive-twin-agent"
        self.secret_account = "ipc-shared-secret"

    def ensure_secret(self) -> str:
        existing = keyring.get_password(self.service_name, self.secret_account)
        if existing:
            return existing
        generated = secrets.token_urlsafe(48)
        keyring.set_password(self.service_name, self.secret_account, generated)
        return generated

    def send(self, command: str, payload: dict[str, Any] | None = None, timeout: float = 3.0) -> dict[str, Any]:
        payload = payload or {}
        secret = self.ensure_secret()
        message = {
            "command": command,
            "payload": payload,
            "nonce": secrets.token_urlsafe(12),
        }
        signature = self._sign(message, secret)
        wire = {**message, "signature": signature}

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(str(self.socket_path))
            sock.sendall((json.dumps(wire, ensure_ascii=True) + "\n").encode("utf-8"))
            response = sock.recv(65536).decode("utf-8").strip()

        return json.loads(response)

    def serve(self, handler: Callable[[str, dict[str, Any]], dict[str, Any]], running_flag: Callable[[], bool]) -> None:
        secret = self.ensure_secret()
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists():
            self.socket_path.unlink()

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(self.socket_path))
            server.listen(8)
            server.settimeout(1.0)

            while running_flag():
                try:
                    conn, _ = server.accept()
                except TimeoutError:
                    continue
                except OSError:
                    continue

                with conn:
                    raw = conn.recv(65536).decode("utf-8").strip()
                    if not raw:
                        conn.sendall(b'{"ok":false,"error":"empty_message"}\n')
                        continue

                    try:
                        incoming = json.loads(raw)
                    except json.JSONDecodeError:
                        conn.sendall(b'{"ok":false,"error":"invalid_json"}\n')
                        continue

                    signature = str(incoming.get("signature", ""))
                    message = {
                        "command": incoming.get("command", ""),
                        "payload": incoming.get("payload", {}),
                        "nonce": incoming.get("nonce", ""),
                    }
                    expected = self._sign(message, secret)
                    if not hmac.compare_digest(signature, expected):
                        conn.sendall(b'{"ok":false,"error":"invalid_signature"}\n')
                        continue

                    cmd = str(message.get("command", ""))
                    payload = message.get("payload", {})
                    if not isinstance(payload, dict):
                        payload = {}

                    try:
                        result = handler(cmd, payload)
                    except Exception as exc:
                        result = {"ok": False, "error": str(exc)}

                    conn.sendall((json.dumps(result, ensure_ascii=True) + "\n").encode("utf-8"))

        if self.socket_path.exists():
            self.socket_path.unlink()

    def _sign(self, message: dict[str, Any], secret: str) -> str:
        canonical = json.dumps(message, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
