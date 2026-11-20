"""
voicebox — Vera's expressive voice engine. Every known emotion has a voice.

The goal (Ankur's, after "Her"): she shouldn't read every line the same flat way.
A real woman sounds *different* when you're grieving vs. thrilled vs. stressed —
her pace, her warmth, the breath between her words all shift. This module is the
designed palette: text → a named TONE → deliberate delivery (speed, warmth,
pauses). Pure logic, no model; the actual voice (Kokoro) is driven by what this
returns, so the two stay consistent.

Design, thought through per stage:
  1. PACE — slow + breathing when the moment is heavy; a lift when it's glad; and
     crucially, SLOWER (to steady, not match) when the user is stressed/anxious.
  2. WARMTH — highest in tender/grief moments, warm-bright in joy.
  3. BREATH — longer pauses (rendered as '…'/commas Kokoro honours) in the weighty
     tones, lighter in the bright ones.

Each tone is a small, honest character — never theatrical, always a caring woman.
The emotion detection here is deliberately explicit (its own lexicon) so the
palette has accurate input even where the deeper affect net is coarse.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Tone:
    name: str
    speed: float      # Kokoro speed multiplier (1.0 = natural; <1 slower)
    warmth: float     # 0..1 — colours wording/soul elsewhere; carried for consistency
    pause: float      # 0..1 — how much she breathes between thoughts
    note: str         # one line: how she sounds in this tone


# ── the palette — every known emotion, each a deliberate voice ─────────────────
# Speeds are centred near 0.95 (her calm companion default) and bounded 0.8–1.12 so
# she never crawls or races. Stressed/anxious are SLOWER than neutral on purpose:
# a calm presence steadies you, it doesn't catch your panic.
TONES: dict[str, Tone] = {
    "grief":    Tone("grief",    0.82, 0.98, 0.9, "slow, hushed, deeply tender — she holds the loss with you"),
    "sad":      Tone("sad",      0.86, 0.92, 0.8, "soft and unhurried, gentle, a little quiet"),
    "stressed": Tone("stressed", 0.88, 0.85, 0.7, "slower and steadying — she doesn't match your rush, she calms it"),
    "anxious":  Tone("anxious",  0.88, 0.85, 0.7, "grounding, even, reassuring — a steady anchor"),
    "upset":    Tone("upset",    0.90, 0.80, 0.6, "measured and warm, not reactive — she stays level with you"),
    "angry":    Tone("angry",    0.92, 0.72, 0.5, "calm and firm, unhurried — steady in the face of heat"),
    "tender":   Tone("tender",   0.86, 1.00, 0.8, "intimate and warm, lingering a little, close"),
    "tired":    Tone("tired",    0.88, 0.90, 0.7, "soft and low, gentle, winding-down with you"),
    "happy":    Tone("happy",    1.05, 0.80, 0.4, "lifted and bright, a smile in the words"),
    "excited":  Tone("excited",  1.10, 0.78, 0.3, "quick and glad, lit up, happy with you"),
    "grateful": Tone("grateful", 0.98, 0.85, 0.5, "warm and full, touched"),
    "neutral":  Tone("neutral",  0.96, 0.60, 0.5, "natural, present, warm — her at rest"),
}


# ── emotion detection — explicit, honest, bounded ─────────────────────────────
# Phrase/word cues per tone, checked in PRIORITY order (first match wins). Grief and
# the heavy tones lead so a real crisis never reads as something lighter.
_CUES: list[tuple[str, tuple[str, ...]]] = [
    ("grief", ("passed away", "passed on", " died", "death of", "lost my", "lost her",
               "lost him", "lost them", "i miss my", "miss my mom", "miss my dad",
               "miss my mother", "miss my father", "grieving", "funeral", "my late",
               "she's gone", "he's gone", "mourning", "widow")),
    ("sad",   ("so sad", "feel sad", "feeling sad", "heartbroken", "depressed", "down",
               "crying", "i cry", "tears", "hopeless", "empty", "lonely", "alone")),
    ("stressed", ("stressed", "overwhelmed", "too much", "can't cope", "can't keep up",
                  "burning out", "under pressure", "so much going on", "drowning")),
    ("anxious", ("anxious", "anxiety", "panicking", "panic", "nervous", "scared",
                 "worried", "worry", "what if", "on edge", "can't stop thinking")),
    ("upset",  ("upset", "frustrated", "fed up", "hurt by", "disappointed", "let down",
                "annoyed")),
    ("angry",  ("angry", "furious", "pissed", "so mad", "rage", "livid", "fuming",
                "can't stand")),
    ("tired",  ("exhausted", "so tired", "worn out", "burnt out", "drained", "no energy",
                "wiped out", "can't go on")),
    ("excited", ("so excited", "can't wait", "thrilled", "pumped", "ecstatic",
                 "over the moon")),
    ("grateful", ("thank you", "thankful", "grateful", "appreciate you", "means a lot")),
    ("happy",  ("happy", "so glad", "great news", "wonderful", "amazing", "delighted",
                "finally did it", "i did it", "we did it", "shipped", "so good",
                "love this", "best day")),
    ("tender", ("i love you", "miss you", "thinking of you", "proud of you",
                "you mean", "so grateful for you", "goodnight", "good night")),
]


def detect(text: str) -> str:
    """The tone name for this text — first cue match wins (heavy tones lead). Falls
    to 'neutral' when nothing emotional is present (she doesn't manufacture feeling)."""
    low = (text or "").lower()
    for name, cues in _CUES:
        if any(c in low for c in cues):
            return name
    return "neutral"


def tone_for(text: str) -> Tone:
    """The full Tone (speed/warmth/pause/note) for this text."""
    return TONES.get(detect(text), TONES["neutral"])


# ── breath: render pauses as punctuation Kokoro honours ───────────────────────
# Kokoro lengthens pauses on '…' (most), then '.', then ','. For the weightier
# tones we gently open up the spacing so she breathes — a comma after a leading
# clause, an ellipsis where a beat belongs — without ever rewriting her words.
_LEADING = re.compile(r"^(oh|well|hey|mm|so|and|but|i'm so sorry|i know)\b", re.IGNORECASE)


def breathe(text: str, tone: Tone) -> str:
    """Add gentle breath to the TEXT for a weighty tone, using only punctuation the
    synth respects. Light-touch: never changes words, never over-punctuates."""
    if tone.pause < 0.6 or not text:
        return text
    t = text.strip()
    # a soft beat after a short opening word ("Oh, …", "Well, …") if not already paused
    m = _LEADING.match(t)
    if m and len(t) > m.end() and t[m.end()] not in ",.…!?":
        t = t[:m.end()] + "," + t[m.end():]
    # in the heaviest tones, let a mid-sentence ' - ' or ' — ' become a real beat
    if tone.pause >= 0.8:
        t = t.replace(" — ", "… ").replace(" - ", "… ")
    return t


# ── laughs & breath texture (the truest "Her" grain) ──────────────────────────
# Kokoro voices soft human tokens naturally ("Ha,", "Mm,", "Aw,", "Heh,"). Used
# SPARINGLY and only when the moment genuinely fits — a warm laugh when she's
# delighted, a soft breath when it's tender — so it reads as real, never sprinkled.
# She already leads many replies with "Oh"/"Hey"; we only add a beat when she
# hasn't, and never on a heavy/serious tone (a laugh there would be jarring).
_ALREADY_LED = re.compile(r"^(oh|hey|mm+|aw+|ha+|heh|well|ooh|yay|haha)\b[,!. ]", re.IGNORECASE)
_TEXTURE: dict[str, tuple[str, ...]] = {
    # a soft laugh / glad breath — only when she's genuinely lifted
    "happy":    ("Oh, ", "Aw, ", "Ha, "),
    "excited":  ("Oh, ", "Yay, ", "Ha, "),
    "grateful": ("Aw, ", "Oh, "),
    # a warm, intimate breath for tender moments (never a laugh here)
    "tender":   ("Mm, ", "Oh, "),
}


def texture(text: str, tone: Tone, *, allow: bool = True) -> str:
    """Optionally lead a reply with a soft, fitting human beat (a warm 'Aw,' when
    she's touched, an 'Oh,' of delight) — the little grain that makes a voice feel
    alive. Only when the tone fits, she hasn't already led with one, and allow is
    set. Deterministic choice (hash of text) so a given line is stable, not random."""
    if not allow or not text:
        return text
    t = text.lstrip()
    if _ALREADY_LED.match(t):
        return text
    opts = _TEXTURE.get(tone.name)
    if not opts:
        return text
    lead = opts[hash(t) % len(opts)]
    # lower-case the first letter so "Aw, " + "That's lovely" reads naturally
    return lead + (t[0].lower() + t[1:] if t[:1].isupper() and not t[:2].isupper() else t)
