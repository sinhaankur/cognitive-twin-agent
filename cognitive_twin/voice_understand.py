"""
voice_understand — she can't read your lips, so she reads what she KNOWS of you.

Voice-to-text is never perfect, especially with an accent or background noise. A
good friend recovers anyway: they hear "remind mugger" and know you said "Munger",
because they know your life. This does that — on the VOICE path only (chat/typing
is already exact) — BEFORE she answers:

  1. REPAIR — fuzzy-match odd words in the transcript against the vocabulary she
     actually knows about you (your people, places, projects, and your learned
     word-lexicon). "shwita" → "Shweta", "monger" → "Munger". Common English words
     are left alone; only out-of-place tokens are considered for repair.
  2. CONFIDENCE — if a word was clearly off and nothing close is known, say so, so
     the caller can ASK ("did you mean …?") instead of guessing. Never confidently
     wrong.

Pure-stdlib (difflib), on-device, no model. Empty vocabulary → it returns the text
unchanged (safe). It only ever swaps a word for one you really use.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field


@dataclass
class Understanding:
    text: str                       # the repaired transcript
    original: str                   # what STT actually produced
    repairs: list[tuple[str, str]] = field(default_factory=list)  # (heard, fixed)
    unsure: list[str] = field(default_factory=list)   # words it couldn't place
    guesses: list[str] = field(default_factory=list)  # best guess for each unsure word
    changed: bool = False

    @property
    def confident(self) -> bool:
        return not self.unsure


# words so ordinary they're never "your vocabulary" — don't try to repair these.
_STOP = {
    "the", "a", "an", "and", "or", "but", "so", "if", "of", "to", "in", "on",
    "at", "for", "with", "is", "are", "was", "were", "be", "do", "does", "did",
    "you", "i", "me", "my", "we", "us", "it", "he", "she", "they", "them",
    "this", "that", "here", "there", "what", "when", "where", "who", "how", "why",
    "can", "could", "would", "should", "will", "want", "need", "tell", "ask",
    "please", "thanks", "thank", "okay", "ok", "yes", "no", "now", "today",
    "hey", "hi", "hello", "her", "him", "about", "remind", "call", "text", "set",
}


def vocabulary() -> dict[str, str]:
    """The words she knows are YOURS → their proper spelling. Keyed by lowercase
    for matching. Pulls from your learned lexicon + the people/places in your life
    story (and is resilient if any source is empty/absent)."""
    vocab: dict[str, str] = {}

    def add(word: str) -> None:
        w = (word or "").strip().strip(".,!?;:\"'()").strip()
        if w and any(c.isalpha() for c in w) and len(w) >= 3:
            vocab.setdefault(w.lower(), w)        # first spelling wins (canonical)

    try:
        from . import pronounce
        for term in pronounce._terms():
            # split multi-word names so "Shweta Sharma" matches each part too
            for part in term.split():
                add(part)
            add(term)
    except Exception:
        pass
    try:
        from . import life_story
        ls = life_story.load()
        for p in getattr(ls, "people", []) or []:
            name = getattr(p, "name", None) or (p.get("name") if isinstance(p, dict) else None)
            if name:
                for part in str(name).split():
                    add(part)
        for place in getattr(ls, "places", []) or []:
            add(str(place))
    except Exception:
        pass
    return vocab


_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")


def understand(text: str, *, vocab: dict[str, str] | None = None) -> Understanding:
    """Repair a voice transcript using what she knows of you. Returns an
    Understanding (repaired text + what changed + anything it couldn't place)."""
    original = (text or "").strip()
    u = Understanding(text=original, original=original)
    if not original:
        return u
    vocab = vocabulary() if vocab is None else vocab
    if not vocab:
        return u                                  # nothing learned → unchanged, safe
    keys = list(vocab.keys())

    def repair_token(tok: str) -> str:
        low = tok.lower()
        if low in _STOP or low in vocab:          # ordinary, or already a known word
            return vocab.get(low, tok)
        # only consider repairing a word that looks "off": not a common English word.
        # a close match to one of YOUR words wins; a near-miss with nothing close is
        # flagged unsure (so she can ask rather than guess).
        close = difflib.get_close_matches(low, keys, n=1, cutoff=0.82)
        if close:
            fixed = vocab[close[0]]
            if fixed.lower() != low:
                u.repairs.append((tok, fixed))
            return fixed
        # a weaker match (0.68–0.82) to a known word → it's probably one of yours but
        # we're not sure which: keep the heard word, note it for a possible "did you
        # mean?" — but ONLY for word-ish tokens long enough to be a real name.
        if len(low) >= 4:
            weak = difflib.get_close_matches(low, keys, n=1, cutoff=0.68)
            if weak:
                u.unsure.append(tok)
                u.guesses.append(vocab[weak[0]])   # remember the guess for "did you mean?"
        return tok

    out = _WORD.sub(lambda m: repair_token(m.group(0)), original)
    u.text = out
    u.changed = out != original
    return u


def clarify_question(u: Understanding) -> str:
    """When she's genuinely unsure of a word, the short question to ASK instead of
    guessing. Empty when she's confident. Uses the guesses captured at parse time
    (so it matches the exact vocabulary that produced this understanding)."""
    if u.confident or not u.unsure:
        return ""
    if u.guesses:
        who = " or ".join(dict.fromkeys(u.guesses[:2]))   # de-dup, keep order
        return f"Sorry — did you mean {who}?"
    return "Sorry, I didn't quite catch that last word — say it once more?"


def status() -> str:
    v = vocabulary()
    if not v:
        return ("understanding: no personal vocabulary yet — I'll recover your "
                "words once I know your people, places, and the words you use.")
    sample = ", ".join(list(v.values())[:8])
    return (f"understanding: I can recover {len(v)} of your words from a mishearing "
            f"(e.g. {sample}), on the voice path.")
