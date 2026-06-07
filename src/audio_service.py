from __future__ import annotations

from dataclasses import dataclass

from multimodal_types import AudioSignal


@dataclass
class AudioServiceConfig:
    enabled: bool = False
    sample_seconds: int = 2
    sample_rate: int = 16000


class AudioService:
    def __init__(self, config: AudioServiceConfig) -> None:
        self.config = config

    def sample(self) -> AudioSignal:
        if not self.config.enabled:
            return AudioSignal(available=False)

        try:
            import numpy as np
            import sounddevice as sd
        except Exception:
            return AudioSignal(available=False)

        frames = int(self.config.sample_seconds * self.config.sample_rate)
        try:
            data = sd.rec(frames, samplerate=self.config.sample_rate, channels=1, dtype="float32")
            sd.wait()
        except Exception:
            return AudioSignal(available=False)

        mono = data[:, 0]
        energy_rms = float((mono**2).mean() ** 0.5)
        voice_detected = energy_rms > 0.01

        speaking_rate_hint = "unknown"
        if voice_detected:
            speaking_rate_hint = "steady" if energy_rms < 0.05 else "animated"

        transcript = ""
        confidence = 0.0

        return AudioSignal(
            available=True,
            voice_detected=voice_detected,
            transcript=transcript,
            transcript_confidence=confidence,
            energy_rms=energy_rms,
            speaking_rate_hint=speaking_rate_hint,
        )
