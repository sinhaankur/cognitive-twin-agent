"""
sentiment — a tiny, on-device, dependency-free sentiment scorer.

Used to give a *mood trend* from words you wrote (social posts, comments). It's a
lexicon method (AFINN-style) with simple negation handling — deliberately small
and transparent, no model download, runs offline in microseconds. It is a rough
signal, not a verdict: everywhere we surface it, we label it as inference.

``score(text) -> float`` in [-1, 1]; 0 = neutral / no signal.

If a richer read is ever wanted, the caller can route text through the local LLM;
this exists so sentiment works with zero dependencies and never leaves the Mac.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import re

# A compact valence lexicon (word → weight, roughly -3..+3). Small on purpose;
# covers the common emotional words that dominate everyday social text.
_LEX: dict[str, int] = {
    # positive
    "good": 2, "great": 3, "love": 3, "loved": 3, "loving": 2, "happy": 3,
    "excited": 3, "amazing": 3, "awesome": 3, "wonderful": 3, "best": 3,
    "beautiful": 3, "grateful": 3, "thankful": 3, "proud": 3, "fun": 2,
    "nice": 2, "glad": 2, "enjoy": 2, "enjoyed": 2, "win": 2, "won": 2,
    "success": 2, "perfect": 3, "brilliant": 3, "yay": 2, "congrats": 3,
    "congratulations": 3, "blessed": 2, "hope": 1, "hopeful": 2, "smile": 2,
    "celebrate": 2, "delighted": 3, "cheers": 1, "thanks": 1, "thank": 1,
    # negative
    "bad": -2, "sad": -3, "hate": -3, "hated": -3, "angry": -3, "terrible": -3,
    "awful": -3, "worst": -3, "horrible": -3, "annoyed": -2, "annoying": -2,
    "tired": -2, "exhausted": -2, "sick": -2, "pain": -2, "hurt": -2,
    "cry": -2, "crying": -2, "depressed": -3, "anxious": -3, "worried": -2,
    "worry": -2, "stress": -2, "stressed": -3, "lonely": -3, "afraid": -2,
    "scared": -2, "fail": -2, "failed": -2, "failure": -2, "lost": -2,
    "sorry": -1, "miss": -1, "missing": -1, "disappointed": -3, "upset": -2,
    "frustrated": -3, "hard": -1, "difficult": -1, "sucks": -3, "ugh": -2,
    "unfortunately": -2, "broke": -1, "broken": -2, "problem": -1, "issue": -1,
}

_NEGATIONS = {"not", "no", "never", "n't", "cant", "cannot", "won't", "dont",
              "don't", "isn't", "wasn't", "without", "hardly", "barely"}

_TOKEN = re.compile(r"[a-z']+")


def score(text: str) -> float:
    """Return a sentiment score in [-1, 1]. 0 when there's no emotional signal."""
    if not text:
        return 0.0
    tokens = _TOKEN.findall(text.lower())
    if not tokens:
        return 0.0
    total = 0.0
    hits = 0
    negate = False
    for tok in tokens:
        if tok in _NEGATIONS or tok.endswith("n't"):
            negate = True
            continue
        w = _LEX.get(tok)
        if w is not None:
            total += (-w if negate else w)
            hits += 1
        # negation only flips the next sentiment-bearing word
        if w is not None:
            negate = False
    if hits == 0:
        return 0.0
    # normalise: average weight (~-3..3) → [-1, 1], gently compressed
    avg = total / hits
    return max(-1.0, min(1.0, avg / 3.0))


if __name__ == "__main__":
    import sys
    for t in (sys.argv[1:] or ["I love this, so happy!", "worst day, so tired and sad",
                               "not good at all", "the meeting is at 3pm"]):
        print(f"{score(t):+.2f}  {t}")
