from __future__ import annotations

from dataclasses import dataclass

from calibration import ThresholdProfile
from multimodal_types import VisionSignal


@dataclass
class CameraServiceConfig:
    enabled: bool = False
    device_index: int = 0
    use_mediapipe: bool = True


class CameraService:
    def __init__(self, config: CameraServiceConfig, thresholds: ThresholdProfile | None = None) -> None:
        self.config = config
        self.thresholds = thresholds or ThresholdProfile()
        self._prev_gray = None
        self._face_mesh = None

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

        face_detected, eye_open_ratio, mouth_open_ratio = self._analyze_face(frame, gray, cv2)
        expression, confidence = self._estimate_expression(
            brightness,
            motion_level,
            face_detected,
            eye_open_ratio,
            mouth_open_ratio,
        )

        return VisionSignal(
            available=True,
            face_detected=face_detected,
            expression=expression,
            expression_confidence=confidence,
            eye_open_ratio=eye_open_ratio,
            mouth_open_ratio=mouth_open_ratio,
            brightness=brightness,
            motion_level=motion_level,
        )

    def _analyze_face(self, frame, gray, cv2) -> tuple[bool, float, float]:
        if self.config.use_mediapipe:
            result = self._analyze_with_mediapipe(frame)
            if result is not None:
                return result

        try:
            cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4)
            return (len(faces) > 0, 0.0, 0.0)
        except Exception:
            return (False, 0.0, 0.0)

    def _analyze_with_mediapipe(self, frame):
        try:
            import cv2
            import mediapipe as mp
        except Exception:
            return None

        if self._face_mesh is None:
            try:
                self._face_mesh = mp.solutions.face_mesh.FaceMesh(
                    static_image_mode=True,
                    max_num_faces=1,
                    refine_landmarks=True,
                    min_detection_confidence=0.5,
                )
            except Exception:
                self._face_mesh = None
                return None

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._face_mesh.process(rgb)
        if not result.multi_face_landmarks:
            return (False, 0.0, 0.0)

        landmarks = result.multi_face_landmarks[0].landmark

        def point(idx: int) -> tuple[float, float]:
            lm = landmarks[idx]
            return lm.x, lm.y

        left_top = point(159)
        left_bottom = point(145)
        right_top = point(386)
        right_bottom = point(374)
        mouth_top = point(13)
        mouth_bottom = point(14)

        eye_open_ratio = ((abs(left_top[1] - left_bottom[1]) + abs(right_top[1] - right_bottom[1])) / 2.0) * 18.0
        mouth_open_ratio = abs(mouth_top[1] - mouth_bottom[1]) * 25.0
        return (True, float(eye_open_ratio), float(mouth_open_ratio))

    def _estimate_expression(
        self,
        brightness: float,
        motion_level: float,
        face_detected: bool,
        eye_open_ratio: float,
        mouth_open_ratio: float,
    ) -> tuple[str, float]:
        if not face_detected:
            return "unknown", 0.0

        # Heuristic-only layer on top of local facial features.
        if eye_open_ratio > 0 and eye_open_ratio < self.thresholds.eye_tired_threshold:
            return "tired", 0.55
        if mouth_open_ratio > 0.09 and motion_level > 0.1:
            return "engaged", 0.58
        if motion_level > 0.18:
            return "engaged", 0.45
        if brightness < 0.25:
            return "tired", 0.4
        return "neutral", 0.5
