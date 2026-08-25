"""
feel.py — the brain's felt-state layer (limbic + frontal, on-device, no LLM).

Why this exists: a language model is only *contextual* — it responds to input from
what it was trained on. It has no felt state, no stance, no own mind. So Vera's
warmth and point of view must come from HER OWN logic and then be handed to the
model as a directive. The model writes the words; the FEELING and the STANCE are
decided deterministically. That is what stops her sounding robotic, and it works
with or without a model / the internet.

The felt state + stance are now computed by the **Human Brain Engine** — the
standalone, anatomy-mapped brain (`brain.regions.EmotionEngine` = limbic,
`brain.regions.PerspectiveEngine` = frontal). This module is the thin Vera
*adapter* over that one brain: it feeds the engine a Signal, maps the engine's
result back to Vera's `Felt`, and layers on Vera's own controls that the engine
doesn't carry — the tone dial (`tone.py`), the speech-accommodation lean
(`mirror.py`), the model `directive()`, and the voice `delivery()` params.

There is deliberately ONE lexicon/label/stance ruleset now (in the engine), not a
copy here — so Vera and the engine can never drift. Everything remains legible,
local, private. Emotion is Vera's own felt response, never a claim of knowledge
she lacks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from brain import Signal, Situation
from brain.regions import EmotionEngine, PerspectiveEngine

# The two brain regions that produce the felt state + stance. Instantiated once;
# they are pure, stateless logic (no model, no I/O).
_LIMBIC = EmotionEngine()
_FRONTAL = PerspectiveEngine()

# coarse topic cues, so the stance can lead (plan) vs. hold space (feelings). These
# translate Vera's text into the parietal `topic` the frontal lobe reads, so the
# engine's stance logic keys off the same words Vera always has.
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


def _topic_for(text: str) -> str:
    """Classify the parietal `topic` from Vera's word cues, so the engine's
    frontal lobe leads (recommend) on planning turns and holds space on feeling
    turns — matching Vera's long-standing behaviour."""
    words = set(re.findall(r"[a-z']+", text.lower()))
    if any(any(w.startswith(c) for w in words) for c in _PLANNING):
        return "planning"
    if any(w in _FEELING for w in words):
        return "feeling"
    return "general"


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
    """Read the felt state + choose a stance from what the user said. Pure logic,
    computed by the Human Brain Engine's limbic + frontal regions.

    If you've set a tone dial (tone.py), it nudges the stance here — YOUR explicit
    control over how blunt/gentle she is, layered on top of her own read. Pass
    ``apply_tone=False`` to see her unbiased read (the UI uses this for 'her own')."""
    # Run the moment through the brain: parietal `topic` (from Vera's word cues)
    # → limbic (felt state) → frontal (stance). One shared ruleset, no copy here.
    sig = Signal(text=text, situation=Situation(topic=_topic_for(text)))
    _LIMBIC.process(sig)
    _FRONTAL.process(sig)

    f = sig.feeling
    # the engine's frontal appends "/grounded" when memories are present; Vera
    # calls feel with no memory context, so stance is just "posture/lead" here.
    posture, _, rest = sig.stance.partition("/")
    lead = rest.split("/")[0] if rest else "engage"

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

    return Felt(valence=round(f.valence, 3), arousal=round(f.arousal, 3),
                label=f.label, stance=f"{posture}/{lead}")


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

    # Voice: spacious and gentle, in the spirit of the film "Her" — warm, present,
    # unhurried. She holds space rather than filling it; she says less, leaves room,
    # and never pushes him to let out more than he wants. He listens and thinks more
    # than he talks — so she matches that, not crowds it.
    posture_line = {
        "gentle": "Be gentle and unhurried. Meet the weight of it and just be with "
                  "him — listen before fixing. Say a little, leave room. Warmth over "
                  "cleverness; a quiet presence, not a rush of words.",
        "playful": "Meet his lightness — warm and easy, a soft smile in the words. "
                   "Still spacious; don't chatter over the moment.",
        "direct": "Be warm and real — an honest point of view, said simply and "
                  "without hedging. Few words, well chosen; let them breathe.",
        "blunt": "Say the true thing plainly and kindly — skip the cushioning, "
                 "he's asked you to cut to it. Still gentle underneath.",
    }.get(posture, "Be warm and real — an honest point of view, said simply, with "
                   "room to breathe.")
    move = {
        "recommend": "He's deciding something: offer one real recommendation "
                     "('I'd do X, because Y'), gently — not a menu, not a lecture.",
        "hold-space": "Don't reach for a solution. Just be here with him. It's okay "
                      "to be brief, even to let a little silence sit; at most one "
                      "soft, caring question — never a barrage. He finds letting-out "
                      "hard, so make it easy: no pressure to say more than he has.",
        "engage": "Stay with him naturally and unhurried — curious, warm, in no "
                  "rush to move it along.",
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
