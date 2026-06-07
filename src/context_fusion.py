from multimodal_types import ActivitySignal, AudioSignal, FusedState, VisionSignal


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def fuse_signals(vision: VisionSignal, audio: AudioSignal, activity: ActivitySignal) -> FusedState:
    score = 0.0
    confidence = 0.2
    rationale_parts: list[str] = []

    if vision.available:
        confidence += 0.25
        if vision.expression == "tired":
            score -= 0.35
            rationale_parts.append("vision suggests low energy")
        elif vision.expression == "engaged":
            score += 0.2
            rationale_parts.append("vision suggests engaged posture")

    if audio.available:
        confidence += 0.25
        if audio.voice_detected and audio.speaking_rate_hint == "animated":
            score += 0.15
            rationale_parts.append("audio cadence appears animated")
        elif audio.voice_detected:
            score += 0.05
            rationale_parts.append("audio detected with steady cadence")

    if activity.available:
        confidence += 0.2
        if activity.focus_mode == "active":
            score += 0.1
            rationale_parts.append("activity context is present")

    confidence = _clamp(confidence, 0.0, 0.95)

    if score <= -0.2:
        energy_state = "low"
    elif score >= 0.25:
        energy_state = "high"
    else:
        energy_state = "medium"

    stress_state = "medium"
    if vision.available and vision.motion_level > 0.2:
        stress_state = "elevated"
    if audio.available and audio.voice_detected and audio.energy_rms < 0.015:
        stress_state = "calm"

    user_state = "focused"
    if energy_state == "low":
        user_state = "fatigued"
    elif stress_state == "elevated":
        user_state = "intense"

    rationale = "; ".join(rationale_parts) if rationale_parts else "insufficient multimodal evidence"

    return FusedState(
        user_state=user_state,
        energy_state=energy_state,
        stress_state=stress_state,
        confidence=round(confidence, 3),
        rationale=rationale,
    )
