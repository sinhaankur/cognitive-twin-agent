from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import socket
import time
from pathlib import Path
from typing import Any, Callable

import keyring


class SignedLocalIPC:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.socket_path = workspace_root / "memory" / "runtime" / "daemon.sock"
        self.service_name = "cognitive-twin-agent"
        self.secret_account = "ipc-shared-secret"
        self.nonce_store_path = workspace_root / "memory" / "runtime" / "ipc_nonce_store.json"
        self.nonce_ttl_seconds = 3600

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
            "ts": int(time.time()),
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
                        "ts": incoming.get("ts", 0),
                    }
                    expected = self._sign(message, secret)
                    if not hmac.compare_digest(signature, expected):
                        conn.sendall(b'{"ok":false,"error":"invalid_signature"}\n')
                        continue

                    nonce = str(message.get("nonce", ""))
                    ts = int(message.get("ts", 0) or 0)
                    if not nonce or not ts:
                        conn.sendall(b'{"ok":false,"error":"missing_nonce_or_timestamp"}\n')
                        continue

                    now = int(time.time())
                    if abs(now - ts) > self.nonce_ttl_seconds:
                        conn.sendall(b'{"ok":false,"error":"stale_message"}\n')
                        continue

                    if self._is_nonce_seen(nonce):
                        conn.sendall(b'{"ok":false,"error":"replay_detected"}\n')
                        continue

                    self._remember_nonce(nonce, ts)

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

    def _is_nonce_seen(self, nonce: str) -> bool:
        store = self._load_nonce_store()
        return nonce in store

    def _remember_nonce(self, nonce: str, ts: int) -> None:
        store = self._load_nonce_store()
        now = int(time.time())
        filtered = {
            n: t
            for n, t in store.items()
            if isinstance(t, int) and now - t <= self.nonce_ttl_seconds
        }
        filtered[nonce] = ts
        self._save_nonce_store(filtered)

    def _load_nonce_store(self) -> dict[str, int]:
        if not self.nonce_store_path.exists():
            return {}
        try:
            raw = json.loads(self.nonce_store_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return {}
            out: dict[str, int] = {}
            for k, v in raw.items():
                try:
                    out[str(k)] = int(v)
                except Exception:
                    continue
            return out
        except Exception:
            return {}

    def _save_nonce_store(self, store: dict[str, int]) -> None:
        self.nonce_store_path.parent.mkdir(parents=True, exist_ok=True)
        self.nonce_store_path.write_text(json.dumps(store, ensure_ascii=True), encoding="utf-8")
