from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
import wave

from calibration import ThresholdProfile
from multimodal_types import AudioSignal
from sentiment_classifier import LocalSentimentClassifier


@dataclass
class AudioServiceConfig:
    enabled: bool = False
    sample_seconds: int = 2
    sample_rate: int = 16000
    enable_transcription: bool = True
    transcription_model: str = "base"
    transcription_compute_type: str = "int8"
    transcription_device: str = "auto"
    model_cache_dir: str = "memory/models"
    sentiment_model: str = "cardiffnlp/twitter-roberta-base-sentiment-latest"


class AudioService:
    def __init__(self, config: AudioServiceConfig, thresholds: ThresholdProfile | None = None) -> None:
        self.config = config
        self.thresholds = thresholds or ThresholdProfile()
        self._whisper_model = None
        self._sentiment = LocalSentimentClassifier(model_name=self.config.sentiment_model)

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
        zero_crossing_rate = float(np.mean(np.abs(np.diff(np.sign(mono))) > 0))
        voice_detected = energy_rms > self.thresholds.voice_energy_threshold

        speaking_rate_hint = "unknown"
        if voice_detected:
            if zero_crossing_rate > 0.16 or energy_rms > self.thresholds.animated_energy_threshold:
                speaking_rate_hint = "animated"
            else:
                speaking_rate_hint = "steady"

        transcript = ""
        confidence = 0.0
        sentiment = "unknown"
        sentiment_confidence = 0.0
        if voice_detected and self.config.enable_transcription:
            transcript, confidence = self._transcribe(mono)
            sentiment_result = self._sentiment.classify(transcript)
            sentiment = sentiment_result.label
            sentiment_confidence = sentiment_result.confidence

        return AudioSignal(
            available=True,
            voice_detected=voice_detected,
            transcript=transcript,
            transcript_confidence=confidence,
            sentiment=sentiment,
            sentiment_confidence=sentiment_confidence,
            energy_rms=energy_rms,
            zero_crossing_rate=zero_crossing_rate,
            speaking_rate_hint=speaking_rate_hint,
        )

    def _transcribe(self, mono) -> tuple[str, float]:
        whisper_model = self._get_whisper_model()
        if whisper_model is None:
            return "", 0.0

        try:
            import numpy as np

            pcm16 = np.clip(mono * 32767.0, -32768, 32767).astype("int16")
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                with wave.open(tmp.name, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(self.config.sample_rate)
                    wf.writeframes(pcm16.tobytes())

                segments, info = whisper_model.transcribe(tmp.name, beam_size=1, vad_filter=True)
                text = " ".join(segment.text.strip() for segment in segments if segment.text).strip()
                confidence = float(getattr(info, "language_probability", 0.0) or 0.0)
                return text, confidence
        except Exception:
            return "", 0.0

    def _get_whisper_model(self):
        if self._whisper_model is not None:
            return self._whisper_model

        try:
            from faster_whisper import WhisperModel

            device = self._resolve_device()
            cache_dir = self._resolve_cache_dir()
            self._whisper_model = WhisperModel(
                self.config.transcription_model,
                device=device,
                compute_type=self.config.transcription_compute_type,
                download_root=cache_dir,
            )
        except Exception:
            self._whisper_model = None

        return self._whisper_model

    def _resolve_device(self) -> str:
        if self.config.transcription_device != "auto":
            return self.config.transcription_device

        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass

        try:
            import ctranslate2

            if ctranslate2.get_cuda_device_count() > 0:
                return "cuda"
        except Exception:
            pass

        return "cpu"

    def _resolve_cache_dir(self) -> str:
        path = Path(self.config.model_cache_dir)
        if not path.is_absolute():
            path = Path(os.getenv("AGENT_WORKSPACE_ROOT", ".")) / path
        path.mkdir(parents=True, exist_ok=True)
        return str(path)
