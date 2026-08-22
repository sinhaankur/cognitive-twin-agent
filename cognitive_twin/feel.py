"""
feel.py — the brain's felt-state layer (limbic + frontal, on-device, no LLM).

Why this exists: a language model is only *contextual* — it responds to input from
what it was trained on. It has no felt state, no stance, no own mind. So Vera's
warmth and point of view must come from HER OWN logic, computed here, and then
handed to the model as a directive. The model writes the words; the FEELING and
the STANCE are decided by this deterministic layer. That is what stops her
sounding robotic, and it works with or without a model / the internet.

This mirrors the Human Brain Engine's limbic (EmotionEngine) + frontal
(PerspectiveEngine) regions. It reads the emotional register of what the user
said and picks a stance, which `agent/loop.py` folds into the system prompt.

Everything here is a legible lexicon + rules — inspectable, local, private.
Emotion is Vera's own felt response, never a claim of knowledge she lacks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# small affective lexicon: word → (valence -1..1, arousal 0..1). Deliberate and
# legible, not learned — so behaviour is inspectable. Extend freely.
_LEXICON: dict[str, tuple[float, float]] = {
    "sad": (-0.7, 0.4), "tired": (-0.4, 0.2), "exhausted": (-0.6, 0.3),
    "worried": (-0.5, 0.6), "anxious": (-0.6, 0.7), "lonely": (-0.7, 0.4),
    "angry": (-0.6, 0.8), "frustrated": (-0.5, 0.7), "stuck": (-0.4, 0.5),
    "afraid": (-0.6, 0.7), "hurt": (-0.7, 0.5), "lost": (-0.5, 0.4),
    "hard": (-0.3, 0.4), "hate": (-0.7, 0.7), "fail": (-0.5, 0.5),
    "overwhelmed": (-0.6, 0.7), "down": (-0.5, 0.3),
    "happy": (0.7, 0.6), "glad": (0.6, 0.5), "excited": (0.7, 0.9),
    "proud": (0.7, 0.6), "love": (0.8, 0.6), "great": (0.6, 0.6),
    "good": (0.4, 0.4), "thanks": (0.4, 0.4), "win": (0.6, 0.7),
    "shipped": (0.6, 0.7), "works": (0.5, 0.5), "finally": (0.4, 0.6),
    "haha": (0.6, 0.7), "lol": (0.6, 0.7), "nice": (0.5, 0.5),
}

_LABELS = [
    (0.5, "bright"), (0.3, "warm"), (0.15, "easy"),
    (-0.15, "steady"), (-0.4, "tender"), (-1.1, "heavy"),
]

# coarse topic cues, so the stance can lead (plan) vs. hold space (feelings).
_PLANNING = {"should", "plan", "next", "focus", "priorit", "todo", "decide"}
_FEELING = {"feel", "feeling", "sad", "lonely", "tired", "worried", "happy", "proud"}


@dataclass
class Felt:
    valence: float
    arousal: float
    label: str
    stance: str          # e.g. "gentle/hold-space", "direct/recommend"

    @property
    def is_light(self) -> bool:
        # positive valence + not maxed-out arousal. Ceiling 0.9 so genuine
        # excitement ("finally shipped it!") still reads as a light moment.
        return self.valence >= 0.15 and self.arousal <= 0.9

    @property
    def is_heavy(self) -> bool:
        return self.valence <= -0.2


def _label(valence: float) -> str:
    for threshold, name in _LABELS:
        if valence >= threshold:
            return name
    return "heavy"


def _tone():
    """Your dial (tone.py), read fresh each turn. Fail-soft to neutral so feel
    never breaks if the store is missing."""
    try:
        from . import tone
        return tone.get()
    except Exception:
        return None


def _mirror_lean():
    """Speech-accommodation lean (mirror.py): how her delivery/wording leans
    toward how you speak, bounded by the identity floor. Fail-soft to None."""
    try:
        from . import mirror
        return mirror.lean()
    except Exception:
        return None


def read(text: str, *, apply_tone: bool = True) -> Felt:
    """Read the felt state + choose a stance from what the user said. Pure logic.

    If you've set a tone dial (tone.py), it nudges the stance here — YOUR explicit
    control over how blunt/gentle she is, layered on top of her own read. Pass
    ``apply_tone=False`` to see her unbiased read (the UI uses this for 'her own')."""
    words = re.findall(r"[a-z']+", text.lower())
    vals = ars = 0.0
    hits = 0
    for w in words:
        if w in _LEXICON:
            v, a = _LEXICON[w]
            vals += v
            ars += a
            hits += 1
    if hits == 0:
        valence = 0.0
        arousal = 0.55 if "!" in text else (0.15 if "?" not in text else 0.35)
    else:
        valence = max(-1.0, min(1.0, vals / hits))
        arousal = max(0.0, min(1.0, ars / hits))
        if "!" in text:
            arousal = min(1.0, arousal + 0.15)

    label = _label(valence)
    heavy = valence <= -0.2
    wordset = set(words)

    # frontal-lobe stance: warmth × whether to lead or hold space
    if heavy:
        posture = "gentle"
    elif valence >= 0.15 and arousal > 0.6:
        posture = "playful"
    else:
        posture = "direct"

    if any(any(w.startswith(c) for w in wordset) for c in _PLANNING):
        lead = "recommend"
    elif heavy or any(w in _FEELING for w in wordset):
        lead = "hold-space"
    else:
        lead = "engage"

    # YOUR dial overrides the posture: strong bluntness sharpens to 'direct'
    # (or 'blunt' at the extreme); strong gentleness softens to 'gentle'. Only
    # when you've actually set it — otherwise her own read stands.
    if apply_tone:
        t = _tone()
        if t and not t.is_default:
            if t.bluntness >= 0.55:
                posture = "blunt" if t.bluntness >= 0.85 else "direct"
            elif t.bluntness <= -0.55:
                posture = "gentle"

    return Felt(valence=round(valence, 3), arousal=round(arousal, 3),
                label=label, stance=f"{posture}/{lead}")


def delivery(text: str) -> dict[str, float]:
    """Cerebellum: turn the felt state into VOICE delivery params (speed, warmth,
    pause) so the actual voice slows + warms in a hard moment and brightens in a
    glad one. Pure math, no model — this is emotion finally reaching the voice.
    Mirrors the Human Brain Engine's MotorEngine so the two stay consistent.

    YOUR tone dial (tone.py) shifts warmth (and, via bluntness, pace) — the human
    holds the last knob on how she sounds."""
    f = read(text)
    speed, warmth, pause = 0.97, 0.5, 0.3
    speed += (f.arousal - 0.4) * 0.12          # arousal quickens
    if f.is_heavy:
        speed -= 0.05                          # slow down, let it breathe
        warmth, pause = 0.85, 0.6
    elif f.is_light:
        warmth = 0.65
    warmth = min(1.0, warmth + abs(f.valence) * 0.15)

    # speech accommodation: lean the voice toward how you speak (energy → pace,
    # warmth → warmth), bounded so she stays herself. Applied before your dial so
    # your explicit control still has the last word.
    ml = _mirror_lean()
    if ml:
        speed += ml.get("energy", 0.0) * 0.06
        warmth = max(0.0, min(1.0, warmth + ml.get("warmth", 0.0) * 0.25))

    # your dial: warmth axis shifts warmth directly; bluntness clips pace/pause
    # (blunter = a touch quicker, less lingering; gentler = slower, warmer)
    t = _tone()
    if t and not t.is_default:
        warmth = max(0.0, min(1.0, warmth + t.warmth * 0.35))
        speed = speed + t.bluntness * 0.04
        if t.bluntness > 0:
            pause = max(0.15, pause - t.bluntness * 0.15)

    speed = round(max(0.85, min(1.08, speed)), 3)
    return {"speed": speed, "warmth": round(warmth, 2), "pause": round(pause, 2)}


def directive(text: str) -> str:
    """A short system-prompt block that hands the model Vera's felt state + stance.
    The model only writes WITHIN this; the feeling itself is decided here, not by
    the model. Returns '' for flatly neutral turns so we don't over-steer."""
    felt = read(text)
    posture, _, lead = felt.stance.partition("/")

    posture_line = {
        "gentle": "Be gentle and unhurried. Meet the weight of it; listen before "
                  "fixing. Warmth over cleverness.",
        "playful": "Match their up energy — a little light and quick, still real.",
        "direct": "Be clear and warm — a real point of view, not hedging.",
        "blunt": "Be blunt and economical. Say the true thing plainly, skip the "
                 "cushioning — they've asked you to cut to it.",
    }.get(posture, "Be clear and warm — a real point of view, not hedging.")
    move = {
        "recommend": "They're deciding something: give an actual recommendation "
                     "('I'd do X because Y'), not a menu of options.",
        "hold-space": "Don't rush to solve it. Be present; ask one caring question "
                      "if natural.",
        "engage": "Engage naturally and move it forward.",
    }[lead]

    # speech accommodation: nudge the WORDING toward how you speak (brevity +
    # register), bounded so she stays herself. A quiet lean, not a command.
    acc = ""
    ml = _mirror_lean()
    if ml:
        parts = []
        if ml.get("brevity", 0) > 0.12:
            parts.append("they write terse — keep it short")
        elif ml.get("brevity", 0) < -0.12:
            parts.append("they write in full — you can open up a little")
        if ml.get("formality", 0) > 0.12:
            parts.append("their register is formal — match it, no slang")
        elif ml.get("formality", 0) < -0.12:
            parts.append("their register is casual — relax yours to match")
        if parts:
            acc = "\nMirror how they speak (stay yourself): " + "; ".join(parts) + "."

    # your dial, if set, is an explicit instruction from the human — honour it
    dial = ""
    t = _tone()
    if t and not t.is_default:
        bits = []
        if t.bluntness >= 0.55:
            bits.append("be blunter than usual")
        elif t.bluntness <= -0.55:
            bits.append("be gentler than usual")
        if t.warmth >= 0.55:
            bits.append("be warmer")
        elif t.warmth <= -0.55:
            bits.append("be more reserved")
        if bits:
            dial = "\nThe user has set your tone: " + ", ".join(bits) + ". Honour it."

    # stay quiet for genuinely flat, neutral turns (don't manufacture emotion) —
    # UNLESS the user set a dial (explicit) or there's a real style lean to carry.
    if felt.label == "steady" and lead == "engage" and not dial and not acc:
        return ""

    return (
        "# HOW YOU FEEL RIGHT NOW (decided by your own mind, not the model)\n"
        f"Felt state: {felt.label} (valence {felt.valence:+.2f}). {posture_line} {move}"
        f"{acc}{dial}\n"
        "This feeling is yours — let it colour the words. Never announce it; live it."
    )
