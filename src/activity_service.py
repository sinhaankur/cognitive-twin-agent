from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from multimodal_types import ActivitySignal


@dataclass
class ActivityServiceConfig:
    enabled: bool = True
    note: str = ""
    context_file: str = ""


class ActivityService:
    def __init__(self, workspace_root: Path, config: ActivityServiceConfig) -> None:
        self.workspace_root = workspace_root
        self.config = config

    def sample(self) -> ActivitySignal:
        if not self.config.enabled:
            return ActivitySignal(available=False)

        context_text = ""
        if self.config.context_file:
            candidate = (self.workspace_root / self.config.context_file).resolve()
            if candidate.exists() and candidate.is_file():
                context_text = candidate.read_text(encoding="utf-8")[:2000]

        note = self.config.note.strip()
        focus_mode = "active" if note or context_text else "unknown"

        return ActivitySignal(
            available=True,
            note=note,
            active_context=context_text,
            focus_mode=focus_mode,
        )
