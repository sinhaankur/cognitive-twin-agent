from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import quantiles


@dataclass
class ThresholdProfile:
    voice_energy_threshold: float = 0.01
    animated_energy_threshold: float = 0.05
    eye_tired_threshold: float = 0.045
    elevated_motion_threshold: float = 0.2
    negative_sentiment_threshold: float = 0.55


class CalibrationManager:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.samples_path = workspace_root / "memory" / "calibration" / "samples.jsonl"
        self.profile_path = workspace_root / "memory" / "calibration" / "threshold_profile.json"

    def record_sample(self, payload: dict) -> None:
        self.samples_path.parent.mkdir(parents=True, exist_ok=True)
        with self.samples_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")

    def compute_profile(self) -> ThresholdProfile:
        samples = self._load_samples()
        if len(samples) < 8:
            return ThresholdProfile()

        energy = [float(item.get("audio_energy_rms", 0.0)) for item in samples if "audio_energy_rms" in item]
        motion = [float(item.get("vision_motion_level", 0.0)) for item in samples if "vision_motion_level" in item]
        eye = [float(item.get("vision_eye_open_ratio", 0.0)) for item in samples if "vision_eye_open_ratio" in item]

        profile = ThresholdProfile()
        if len(energy) >= 8:
            q1, q2, q3 = quantiles(energy, n=4)
            profile.voice_energy_threshold = max(0.006, round(q1 * 0.75, 5))
            profile.animated_energy_threshold = round(q3, 5)

        if len(motion) >= 8:
            _, _, q3 = quantiles(motion, n=4)
            profile.elevated_motion_threshold = round(max(0.1, q3), 5)

        nonzero_eye = [v for v in eye if v > 0]
        if len(nonzero_eye) >= 8:
            q1, _, _ = quantiles(nonzero_eye, n=4)
            profile.eye_tired_threshold = round(max(0.02, q1), 5)

        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.profile_path.write_text(json.dumps(asdict(profile), ensure_ascii=True, indent=2), encoding="utf-8")
        return profile

    def load_profile(self) -> ThresholdProfile:
        if not self.profile_path.exists():
            return ThresholdProfile()

        try:
            raw = json.loads(self.profile_path.read_text(encoding="utf-8"))
            return ThresholdProfile(
                voice_energy_threshold=float(raw.get("voice_energy_threshold", 0.01)),
                animated_energy_threshold=float(raw.get("animated_energy_threshold", 0.05)),
                eye_tired_threshold=float(raw.get("eye_tired_threshold", 0.045)),
                elevated_motion_threshold=float(raw.get("elevated_motion_threshold", 0.2)),
                negative_sentiment_threshold=float(raw.get("negative_sentiment_threshold", 0.55)),
            )
        except Exception:
            return ThresholdProfile()

    def _load_samples(self) -> list[dict]:
        if not self.samples_path.exists():
            return []

        out = []
        with self.samples_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                    if isinstance(payload, dict):
                        out.append(payload)
                except Exception:
                    continue
        return out
