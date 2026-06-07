from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class VisionSignal:
    available: bool
    face_detected: bool = False
    expression: str = "unknown"
    expression_confidence: float = 0.0
    brightness: float = 0.0
    motion_level: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class AudioSignal:
    available: bool
    voice_detected: bool = False
    transcript: str = ""
    transcript_confidence: float = 0.0
    energy_rms: float = 0.0
    speaking_rate_hint: str = "unknown"
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class ActivitySignal:
    available: bool
    note: str = ""
    active_context: str = ""
    focus_mode: str = "unknown"
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class FusedState:
    user_state: str
    energy_state: str
    stress_state: str
    confidence: float
    rationale: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


def to_payload(obj: Any) -> dict[str, Any]:
    return asdict(obj)
