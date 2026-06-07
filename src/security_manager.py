from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
import keyring


@dataclass
class SecurityState:
    allowed_users: list[str]
    token_salt: str
    token_hash: str


class SecurityManager:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.state_file = workspace_root / "memory" / "security" / "security_state.json"
        self._key_service_name = "cognitive-twin-agent"
        self._key_account_name = "state-encryption-key"

    def init_user(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        salt = secrets.token_hex(16)
        token_hash = self._hash_token(token, salt)

        state = SecurityState(
            allowed_users=[username],
            token_salt=salt,
            token_hash=token_hash,
        )
        self._ensure_key()
        self._save(state)
        return token

    def add_allowed_user(self, username: str) -> None:
        state = self._load()
        if username not in state.allowed_users:
            state.allowed_users.append(username)
            self._save(state)

    def verify(self, presented_token: str) -> tuple[bool, str]:
        state = self._load()
        current_user = getpass.getuser()
        if current_user not in state.allowed_users:
            return False, f"Current OS user '{current_user}' is not allowed"

        expected_hash = state.token_hash
        actual_hash = self._hash_token(presented_token, state.token_salt)
        if not hmac.compare_digest(expected_hash, actual_hash):
            return False, "Invalid token"

        return True, "ok"

    def status(self) -> dict:
        state = self._load()
        return {
            "allowed_users": state.allowed_users,
            "security_state_file": str(self.state_file.relative_to(self.workspace_root)),
        }

    def _hash_token(self, token: str, salt: str) -> str:
        payload = (salt + token).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _load(self) -> SecurityState:
        if not self.state_file.exists():
            raise RuntimeError("Security is not initialized. Run init first.")

        encrypted = self.state_file.read_text(encoding="utf-8")
        raw_payload = self._decrypt(encrypted)
        raw = json.loads(raw_payload)
        return SecurityState(
            allowed_users=raw.get("allowed_users", []),
            token_salt=raw.get("token_salt", ""),
            token_hash=raw.get("token_hash", ""),
        )

    def _save(self, state: SecurityState) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "allowed_users": state.allowed_users,
            "token_salt": state.token_salt,
            "token_hash": state.token_hash,
        }
        encrypted = self._encrypt(json.dumps(data, ensure_ascii=True))
        self.state_file.write_text(encrypted, encoding="utf-8")

    def _ensure_key(self) -> bytes:
        existing = keyring.get_password(self._key_service_name, self._key_account_name)
        if existing:
            return existing.encode("utf-8")

        generated = Fernet.generate_key()
        keyring.set_password(self._key_service_name, self._key_account_name, generated.decode("utf-8"))
        return generated

    def _load_key(self) -> bytes:
        existing = keyring.get_password(self._key_service_name, self._key_account_name)
        if not existing:
            raise RuntimeError("Encryption key not found in OS keychain. Re-run init.")
        return existing.encode("utf-8")

    def _encrypt(self, plaintext: str) -> str:
        key = self._ensure_key()
        fernet = Fernet(key)
        token = fernet.encrypt(plaintext.encode("utf-8"))
        return token.decode("utf-8")

    def _decrypt(self, encrypted_text: str) -> str:
        key = self._load_key()
        fernet = Fernet(key)
        try:
            plain = fernet.decrypt(encrypted_text.encode("utf-8"))
        except InvalidToken as exc:
            raise RuntimeError("Security state decryption failed") from exc
        return plain.decode("utf-8")
