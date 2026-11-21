"""
pronounce — Vera learns YOUR words: the names, terms, and Hindi/English mix you
actually say, so she stops mishearing them.

Whisper is trained on general speech, so it fumbles personal vocabulary — your
name, people's names, places, and Hindi words dropped into English ("Vera, light
on karo"). The fix that works on-device is a small PERSONAL LEXICON that we feed
to the recogniser as a hint (`initial_prompt`): a list of the words you use biases
it toward hearing them right. No retraining, no cloud — just a sealed list that
grows as you talk.

Two ways it fills:
  • you add a word (or a mishearing → correction) explicitly, and
  • PASSIVELY: when you repeat yourself or correct her, the words she kept are
    remembered, so the same mistake fades over time.

It's the written vocabulary only — never audio. Sealed on-device, opt-in-safe
(empty by default; an empty lexicon changes nothing).

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

from typing import Any

from . import security

_STORE = "pronounce.json"               # sealed personal lexicon
_MAX_TERMS = 160                        # keep the hint prompt short + relevant
_MAX_PROMPT_CHARS = 220                 # Whisper weights early tokens; keep it tight


def _load() -> dict[str, Any]:
    d = security.read_state(security.path(_STORE), default={})
    return d if isinstance(d, dict) else {}


def _save(d: dict[str, Any]) -> None:
    security.write_state(security.path(_STORE), d)


def _terms() -> dict[str, int]:
    """word → weight (how often it's mattered). Higher = kept nearer the front."""
    t = _load().get("terms", {})
    return t if isinstance(t, dict) else {}


def add(*words: str, weight: int = 1) -> int:
    """Teach her a word (or a few) you use — a name, a place, a Hindi term. Returns
    how many are now known. Case + surrounding punctuation are normalised lightly."""
    t = _terms()
    for w in words:
        w = (w or "").strip().strip(".,!?;:\"'()").strip()
        if not w or len(w) > 40:
            continue
        # keep multi-word names whole ("Shweta Sharma"); drop pure numbers/noise.
        if any(ch.isalpha() for ch in w):
            t[w] = t.get(w, 0) + weight
    # cap: keep the most-weighted terms
    if len(t) > _MAX_TERMS:
        t = dict(sorted(t.items(), key=lambda kv: -kv[1])[:_MAX_TERMS])
    d = _load()
    d["terms"] = t
    _save(d)
    return len(t)


def learn_correction(misheard: str, correct: str) -> None:
    """She heard `misheard`, you meant `correct` — remember the correct words so the
    same slip fades. Called passively when you fix her. Weighted higher (you cared
    enough to correct)."""
    if correct:
        add(*correct.split(), weight=2)


def note_accepted(text: str) -> None:
    """A turn you accepted (didn't correct) — gently reinforce its less-common words
    so your real vocabulary rises to the top of the hint. Common words are skipped."""
    if not text:
        return
    rare = [w for w in text.split() if len(w) >= 4 and w.lower() not in _COMMON]
    if rare:
        add(*rare[:6], weight=1)


def forget(word: str) -> None:
    t = _terms()
    t.pop(word, None)
    d = _load(); d["terms"] = t; _save(d)


def clear() -> None:
    _save({})


def prompt() -> str:
    """The `initial_prompt` hint for Whisper: your top words, most-weighted first,
    trimmed to a short budget. Empty when nothing's learned (changes nothing)."""
    t = _terms()
    if not t:
        return ""
    ordered = [w for w, _ in sorted(t.items(), key=lambda kv: -kv[1])]
    out, used = [], 0
    for w in ordered:
        if used + len(w) + 2 > _MAX_PROMPT_CHARS:
            break
        out.append(w)
        used += len(w) + 2
    # a natural-language frame reads better to Whisper than a bare word list
    return ("Vera, an on-device assistant. The speaker may mix English and Hindi. "
            "Names and words they use: " + ", ".join(out) + ".") if out else ""


def is_active() -> bool:
    return bool(_terms())


def status() -> str:
    t = _terms()
    if not t:
        return ("pronunciation: learning nothing yet — teach me your words with "
                "`ctwin words add <word>`, or I'll pick them up as we talk.")
    top = ", ".join(w for w, _ in sorted(t.items(), key=lambda kv: -kv[1])[:8])
    return f"pronunciation: {len(t)} of your words learned (e.g. {top}), sealed on-device."


# words too common to be worth biasing toward (don't crowd out your real vocabulary)
_COMMON = {
    "that", "this", "with", "have", "from", "they", "them", "then", "there",
    "what", "when", "where", "which", "would", "could", "should", "about",
    "your", "yours", "mine", "just", "like", "want", "need", "know", "think",
    "really", "going", "gonna", "please", "thanks", "thank", "okay", "yeah",
    "good", "nice", "well", "much", "more", "some", "here", "come", "tell",
}


def _main(argv: list[str]) -> int:
    import sys
    args = argv[1:] if argv and argv[0] in ("words", "pronounce") else argv
    if not args or args[0] == "status":
        print(status()); return 0
    if args[0] == "add" and len(args) > 1:
        n = add(*args[1:], weight=2)
        print(f"✓ Learned. {n} of your words known now."); return 0
    if args[0] == "forget" and len(args) > 1:
        forget(args[1]); print(f"✓ Forgot “{args[1]}”."); return 0
    if args[0] == "clear":
        clear(); print("✓ Cleared your word list."); return 0
    if args[0] == "prompt":
        print(prompt() or "(empty)"); return 0
    print("usage: ctwin words [status|add <word...>|forget <word>|clear|prompt]")
    return 2


if __name__ == "__main__":        # pragma: no cover
    import sys
    raise SystemExit(_main(sys.argv[1:]))
