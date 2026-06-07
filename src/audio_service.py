from __future__ import annotations

from dataclasses import dataclass
import tempfile
import wave

from multimodal_types import AudioSignal


@dataclass
class AudioServiceConfig:
    enabled: bool = False
    sample_seconds: int = 2
    sample_rate: int = 16000
    enable_transcription: bool = True
    transcription_model: str = "base"
    transcription_compute_type: str = "int8"


class AudioService:
    def __init__(self, config: AudioServiceConfig) -> None:
        self.config = config
        self._whisper_model = None

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
        voice_detected = energy_rms > 0.01

        speaking_rate_hint = "unknown"
        if voice_detected:
            if zero_crossing_rate > 0.16 or energy_rms > 0.05:
                speaking_rate_hint = "animated"
            else:
                speaking_rate_hint = "steady"

        transcript = ""
        confidence = 0.0
        sentiment = "unknown"
        sentiment_confidence = 0.0
        if voice_detected and self.config.enable_transcription:
            transcript, confidence = self._transcribe(mono)
            sentiment, sentiment_confidence = self._infer_sentiment(transcript)

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

            self._whisper_model = WhisperModel(
                self.config.transcription_model,
                compute_type=self.config.transcription_compute_type,
            )
        except Exception:
            self._whisper_model = None

        return self._whisper_model

    def _infer_sentiment(self, transcript: str) -> tuple[str, float]:
        if not transcript:
            return "unknown", 0.0

        text = transcript.lower()
        positive = {"good", "great", "happy", "nice", "calm", "done", "progress"}
        negative = {"bad", "tired", "stressed", "angry", "blocked", "frustrated", "late"}

        pos_hits = sum(1 for token in positive if token in text)
        neg_hits = sum(1 for token in negative if token in text)
        total = pos_hits + neg_hits

        if total == 0:
            return "neutral", 0.35

        if pos_hits > neg_hits:
            return "positive", min(0.85, 0.45 + (pos_hits - neg_hits) * 0.12)
        if neg_hits > pos_hits:
            return "negative", min(0.85, 0.45 + (neg_hits - pos_hits) * 0.12)
        return "neutral", 0.45
