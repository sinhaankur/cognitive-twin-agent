from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from multimodal_types import VisionSignal


@dataclass
class CameraServiceConfig:
    enabled: bool = False
    device_index: int = 0


class CameraService:
    def __init__(self, config: CameraServiceConfig) -> None:
        self.config = config
        self._prev_gray = None

    def sample(self) -> VisionSignal:
        if not self.config.enabled:
            return VisionSignal(available=False)

        try:
            import cv2
            import numpy as np
        except Exception:
            return VisionSignal(available=False)

        cap = cv2.VideoCapture(self.config.device_index)
        if not cap.isOpened():
            return VisionSignal(available=False)

        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            return VisionSignal(available=False)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean() / 255.0)

        motion_level = 0.0
        if self._prev_gray is not None:
            diff = cv2.absdiff(gray, self._prev_gray)
            motion_level = float(diff.mean() / 255.0)
        self._prev_gray = gray

        face_detected = self._detect_face(gray, cv2)
        expression, confidence = self._estimate_expression(brightness, motion_level, face_detected)

        return VisionSignal(
            available=True,
            face_detected=face_detected,
            expression=expression,
            expression_confidence=confidence,
            brightness=brightness,
            motion_level=motion_level,
        )

    def _detect_face(self, gray, cv2) -> bool:
        try:
            cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4)
            return len(faces) > 0
        except Exception:
            return False

    def _estimate_expression(self, brightness: float, motion_level: float, face_detected: bool) -> tuple[str, float]:
        if not face_detected:
            return "unknown", 0.0

        # Heuristic-only fallback until a dedicated expression model is connected.
        if motion_level > 0.18:
            return "engaged", 0.45
        if brightness < 0.25:
            return "tired", 0.4
        return "neutral", 0.5
