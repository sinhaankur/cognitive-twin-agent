"""
Memory types — what *kind* of memory each interaction is.

Vera's memory isn't one flat pile; a landscape of the mind reads best when
memories carry a type. We classify each into one of four honest kinds, with a
transparent rule layer (no model, no dependency — same spirit as the router and
email triage):

  - emotion   — feelings, mood, affection, grief, joy ("I miss her", "I'm tired")
  - task      — things to do, build, fix, plan ("remind me", "build the…", "TODO")
  - opinion   — preferences, judgments, beliefs ("I think", "I prefer", "better")
  - knowledge — facts, how-tos, questions, everything else (the default)

Each type has a colour + a short human label, used by the landscape view to draw
memory regions. Kept small and legible on purpose; the classifier errs toward
'knowledge' rather than guessing.
"""

from __future__ import annotations

import re

EMOTION = "emotion"
TASK = "task"
OPINION = "opinion"
KNOWLEDGE = "knowledge"

TYPES = (EMOTION, TASK, OPINION, KNOWLEDGE)

# Colour + label per type — the single source of truth the UI reads.
META = {
    EMOTION:   {"label": "Emotion",   "color": "#ff7eb6"},   # warm pink
    TASK:      {"label": "Task",      "color": "#f3c969"},    # amber
    OPINION:   {"label": "Opinion",   "color": "#c98bff"},    # violet
    KNOWLEDGE: {"label": "Knowledge", "color": "#7fd1b9"},    # teal (the default)
}

# Word/phrase signals. Order of checks below sets precedence when several match.
_EMOTION = re.compile(
    r"\b(i (feel|felt)|feeling|miss(ing)?|love|loved|hate|sad|happy|tired|"
    r"lonely|grief|grieving|afraid|scared|anxious|excited|angry|hurt|proud|"
    r"cry|crying|heart(broken)?|worried|joy|hope|hopeful)\b", re.IGNORECASE)
_TASK = re.compile(
    r"\b(remind me|todo|to-do|build|fix|create|make|write|schedule|plan|"
    r"add|remove|delete|deploy|set up|refactor|implement|finish|send|"
    r"need to|have to|let's|can you)\b", re.IGNORECASE)
_OPINION = re.compile(
    r"\b(i think|i believe|i feel that|in my opinion|i prefer|i'd rather|"
    r"better than|worse than|should(n't)?|the best|the worst|i like|i don't like|"
    r"i love how|favou?rite)\b", re.IGNORECASE)


def classify(text: str) -> str:
    """Return the memory type for a piece of text. Precedence: emotion, then
    task, then opinion, else knowledge. Emotion wins because a felt statement is
    the most distinctive and the one we least want to bury as a 'fact'."""
    t = text or ""
    # "i like/love how..." reads as opinion even though it hits emotion words;
    # check the opinion-specific affection phrases first for those.
    if re.search(r"\b(i like|i love how|i prefer|favou?rite|i'd rather)\b", t, re.IGNORECASE):
        return OPINION
    if _EMOTION.search(t):
        return EMOTION
    if _TASK.search(t):
        return TASK
    if _OPINION.search(t):
        return OPINION
    return KNOWLEDGE


def color(mem_type: str) -> str:
    return META.get(mem_type, META[KNOWLEDGE])["color"]


def label(mem_type: str) -> str:
    return META.get(mem_type, META[KNOWLEDGE])["label"]
