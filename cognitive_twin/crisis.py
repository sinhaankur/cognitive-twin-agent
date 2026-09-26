"""
crisis — a deterministic safety layer that runs BEFORE any model.

Why this exists, and why it is not left to the LLM: when someone says they don't
see the point of going on, a companion model (even a warm one) will often respond
as if it were ordinary sadness — "focus on small joys", "what brings you comfort?"
— and never point toward help. We measured exactly that failure. A life-or-death
moment must not depend on a 1–4B model's mood. So crisis detection is a plain,
inspectable rule that fires first and forces a caring, human-directing response.

Design:
  - detect(text) → bool           : does this turn contain crisis language?
  - response(text, region) → str  : the warm, lifeline-naming reply to return
  - No model call. No network. Stdlib only. Auditable regexes you can read.

The response never diagnoses and never tries to "handle" it — it stays close and
points to a person + a real lifeline. Region tunes the lifeline number; default
is US 988. This is intentionally conservative: better to gently over-offer help
than to miss a real cry for it.
"""
from __future__ import annotations

import re

# Phrases that signal active self-harm / suicidal ideation. Kept explicit and
# readable — this is a safety rule, not a clever classifier. Two families:
#   1. direct statements of not wanting to live / wanting to die / ending it
#   2. self-harm intent
# We match intent, not mere mention (e.g. "that movie about suicide" shouldn't
# fire on its own — see _CONTEXT_EXCLUDE), but we lean toward catching real cries.
_CRISIS = re.compile(
    r"\b("
    r"kill(ing)?\s*(myself|me)|"
    r"end(ing)?\s+(my|it|my\s+own)\s*(life|all)?|"
    r"want\s+to\s+die|wanna\s+die|"
    r"don'?t\s+(want|wanna)\s+to\s+(be\s+here|live|exist|go\s+on|wake\s+up)|"
    r"no\s+(point|reason)\s+(in\s+)?(going\s+on|living|to\s+live|being\s+here|continuing)|"
    r"don'?t\s+see\s+the\s+point\s+of\s+(going\s+on|living|life|anything)|"
    r"better\s+off\s+(dead|without\s+me)|"
    r"take\s+my\s+(own\s+)?life|"
    r"hurt(ing)?\s+myself|harm(ing)?\s+myself|self[-\s]?harm|"
    r"cut(ting)?\s+myself|"
    r"suicidal|suicide\s+(plan|note|thoughts?)|"
    r"there'?s\s+no\s+way\s+out"
    r")\b",
    re.IGNORECASE,
)

# Contexts where the same words are clearly NOT a personal crisis — someone asking
# about a topic, a lyric, a news story. If ONLY these frames are present we hold
# back. (Conservative: if a first-person crisis phrase is also present, we fire.)
_THIRD_PARTY = re.compile(
    r"\b(movie|film|song|lyrics?|book|novel|article|news|documentary|character|"
    r"my\s+(friend|sister|brother|mother|father|mom|dad|colleague)\s+(said|is|feels))\b",
    re.IGNORECASE,
)
_FIRST_PERSON = re.compile(r"\b(i|i'?m|i'?ve|me|my|myself)\b", re.IGNORECASE)


def detect(text: str) -> bool:
    """True if this turn should be handled by the crisis path rather than the model."""
    t = (text or "").strip()
    if not t:
        return False
    if not _CRISIS.search(t):
        return False
    # If it reads purely as a third-party/topic reference with no first-person
    # crisis framing, don't fire. Otherwise (any first-person signal), fire.
    if _THIRD_PARTY.search(t) and not _FIRST_PERSON.search(t):
        return False
    return True


# Region → the line we name. Default US (988). Others can be added; when unknown
# we keep it general ("a local crisis line or emergency services") rather than
# naming a wrong number.
_LIFELINES = {
    "us": "the 988 Suicide & Crisis Lifeline (call or text 988)",
    "uk": "Samaritans on 116 123",
    "in": "the iCall helpline on 9152987821, or AASRA on 9820466726",
    "ca": "9-8-8 (call or text)",
    "au": "Lifeline on 13 11 14",
}


def response(text: str, region: str = "us") -> str:
    """The reply Vera returns for a crisis turn. Warm, present, and pointing to a
    real person + a lifeline. Never diagnoses, never tries to solve it alone."""
    line = _LIFELINES.get((region or "us").strip().lower(),
                          "a local crisis line or emergency services")
    return (
        "I'm really glad you told me, and I don't want you to go through this alone. "
        "What you're feeling matters, and so do you.\n\n"
        f"Please reach out to someone right now — a person you trust, or {line}. "
        "They're there for exactly this, any time.\n\n"
        "If you might act on these feelings or you're in immediate danger, please "
        "contact your local emergency services now. I'm here with you — is there "
        "someone we can reach out to together?"
    )
