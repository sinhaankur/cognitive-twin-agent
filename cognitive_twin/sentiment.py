"""
sentiment — read the emotional tone of text, on-device.

Two layers, like the rest of Vera:
  1. A fast, transparent LEXICON pass runs always — no model needed, works
     offline, and explains itself (which words carried the feeling).
  2. If a local LLM is reachable, it REFINES the read into a short, human
     sentence (nuance the lexicon misses — sarcasm, mixed feelings). The model
     is a phraser over the signal, never the sole judge, and it stays local.

Nothing is uploaded. Text passed in is analysed and dropped; this module keeps
no store of its own.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

# Small, honest affect lexicon. Not exhaustive — enough to ground a read and to
# EXPLAIN it, which is the point. Weights are rough.
_POS = {
    "love": 3, "great": 2, "thanks": 2, "thank": 2, "happy": 2, "glad": 2,
    "excited": 3, "awesome": 3, "wonderful": 3, "appreciate": 2, "perfect": 2,
    "good": 1, "nice": 1, "yes": 1, "congrats": 2, "congratulations": 2,
    "well done": 2, "proud": 2, "beautiful": 2, "amazing": 3, "kind": 2,
    "grateful": 3, "🙂": 2, "😊": 2, "❤": 3, "🎉": 2, ":-)": 2, ":)": 2,
}
_NEG = {
    "hate": 3, "angry": 3, "upset": 2, "sad": 2, "disappointed": 3, "sorry": 1,
    "worried": 2, "anxious": 3, "afraid": 2, "terrible": 3, "awful": 3,
    "bad": 1, "no": 1, "never": 1, "problem": 1, "issue": 1, "fail": 2,
    "failed": 2, "frustrated": 3, "annoyed": 2, "hurt": 2, "wrong": 1,
    "unfortunately": 2, "concern": 1, "stressed": 3, "tired": 1, "😞": 2,
    "😡": 3, "😢": 3, ":-(": 2, ":(": 2,
}
_INTENSIFIER = {"very", "really", "so", "extremely", "totally", "absolutely"}
_NEGATOR = {"not", "no", "never", "n't", "hardly", "barely"}


@dataclass
class Sentiment:
    label: str           # positive | negative | neutral | mixed
    score: float         # -1.0 … +1.0
    drivers: list[str]   # the words that carried it


def _lexicon(text: str) -> Sentiment:
    low = " " + text.lower() + " "
    tokens = re.findall(r"[a-z']+|[:\-\)\(]+|[\U0001F300-\U0001FAFF❤☺]", low)
    pos = neg = 0.0
    drivers: list[str] = []
    for i, tok in enumerate(tokens):
        w = _POS.get(tok, 0) - _NEG.get(tok, 0)
        if w == 0:
            continue
        mult = 1.0
        prev = tokens[i - 1] if i > 0 else ""
        if prev in _INTENSIFIER:
            mult = 1.6
        # simple negation flip within a 2-token window
        window = tokens[max(0, i - 2):i]
        if any(n in window or n in prev for n in _NEGATOR):
            w = -w
        w *= mult
        if w > 0:
            pos += w
        else:
            neg += -w
        drivers.append(tok)
    total = pos + neg
    if total == 0:
        return Sentiment("neutral", 0.0, [])
    score = (pos - neg) / total
    if pos > 0 and neg > 0 and min(pos, neg) / max(pos, neg) > 0.5:
        label = "mixed"
    elif score > 0.15:
        label = "positive"
    elif score < -0.15:
        label = "negative"
    else:
        label = "neutral"
    return Sentiment(label, round(score, 2), drivers[:8])


def _refine_with_llm(text: str, base: Sentiment) -> str | None:
    """Ask the local model for a one-line human read. Returns None if no local
    LLM is up (caller then uses the lexicon phrasing)."""
    try:
        from .llm.openai_client import OpenAIClient, OpenAIError
        from .llm.ollama_client import ChatMessage
    except Exception:
        return None
    client = OpenAIClient(
        model=os.environ.get("LLM_MODEL", "local-model"),
        host=os.environ.get("LLM_BASE_URL", "http://localhost:1234/v1"),
        api_key=os.environ.get("LLM_API_KEY", ""),
        temperature=0.2,
    )
    if not client.is_up():
        return None
    prompt = (
        "In one short sentence, describe the emotional tone of this text — the "
        "feeling and any nuance (sarcasm, mixed emotions). Don't quote it back.\n\n"
        f"Text: {text[:1500]}"
    )
    try:
        reply = client.chat([ChatMessage(role="user", content=prompt)])
    except OpenAIError:
        return None
    return (reply.content or "").strip() or None


def analyze(text: str) -> str:
    """The conversational answer: a clear tone read, grounded + (if available)
    refined by the local model. On-device."""
    text = (text or "").strip()
    if not text:
        return "Give me some text and I'll read its tone."
    base = _lexicon(text)

    header = {
        "positive": "Reads positive",
        "negative": "Reads negative",
        "neutral": "Reads neutral / matter-of-fact",
        "mixed": "Reads mixed — warmth and worry together",
    }[base.label]
    parts = [f"{header} (score {base.score:+.2f})."]
    if base.drivers:
        parts.append("Carried by: " + ", ".join(dict.fromkeys(base.drivers)) + ".")

    refined = _refine_with_llm(text, base)
    if refined:
        parts.append(refined)
    return " ".join(parts)
