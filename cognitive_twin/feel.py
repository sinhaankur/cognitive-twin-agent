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


def read(text: str) -> Felt:
    """Read the felt state + choose a stance from what the user said. Pure logic."""
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

    return Felt(valence=round(valence, 3), arousal=round(arousal, 3),
                label=label, stance=f"{posture}/{lead}")


def directive(text: str) -> str:
    """A short system-prompt block that hands the model Vera's felt state + stance.
    The model only writes WITHIN this; the feeling itself is decided here, not by
    the model. Returns '' for flatly neutral turns so we don't over-steer."""
    felt = read(text)
    posture, _, lead = felt.stance.partition("/")

    tone = {
        "gentle": "Be gentle and unhurried. Meet the weight of it; listen before "
                  "fixing. Warmth over cleverness.",
        "playful": "Match their up energy — a little light and quick, still real.",
        "direct": "Be clear and warm — a real point of view, not hedging.",
    }[posture]
    move = {
        "recommend": "They're deciding something: give an actual recommendation "
                     "('I'd do X because Y'), not a menu of options.",
        "hold-space": "Don't rush to solve it. Be present; ask one caring question "
                      "if natural.",
        "engage": "Engage naturally and move it forward.",
    }[lead]

    # stay quiet for genuinely flat, neutral turns (don't manufacture emotion)
    if felt.label == "steady" and lead == "engage":
        return ""

    return (
        "# HOW YOU FEEL RIGHT NOW (decided by your own mind, not the model)\n"
        f"Felt state: {felt.label} (valence {felt.valence:+.2f}). {tone} {move}\n"
        "This feeling is yours — let it colour the words. Never announce it; live it."
    )
