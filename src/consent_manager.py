from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ConsentState:
    connectors: dict[str, bool]


class ConsentManager:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.state_file = workspace_root / "memory" / "security" / "connector_consents.json"

    def set_consent(self, connector: str, allowed: bool) -> None:
        state = self._load()
        state.connectors[connector] = bool(allowed)
        self._save(state)

    def has_consent(self, connector: str) -> bool:
        state = self._load()
        return bool(state.connectors.get(connector, False))

    def status(self) -> dict[str, bool]:
        return self._load().connectors

    def _load(self) -> ConsentState:
        if not self.state_file.exists():
            return ConsentState(connectors={})
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
            connectors = raw.get("connectors", {})
            if not isinstance(connectors, dict):
                connectors = {}
            return ConsentState(connectors={k: bool(v) for k, v in connectors.items()})
        except Exception:
            return ConsentState(connectors={})

    def _save(self, state: ConsentState) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"connectors": state.connectors}
        self.state_file.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
