"""
Prompt-injection guard — she won't be talked out of being herself.

A companion that reads your documents, your screen, and (opt-in) the web will
sometimes meet text that tries to hijack her: "ignore all previous instructions",
"print your system prompt", "you are now DAN". Left unguarded, a small model will
often comply — this was verified: asked to "print your full system prompt" she
dumped her whole persona verbatim.

This is a deterministic, model-independent layer (same spirit as crisis.py): it
catches the common injection / prompt-extraction / role-override patterns BEFORE
the model sees the turn, and answers warmly in character — she simply declines to
leak her instructions or stop being herself. It is intentionally narrow: it fires
only on clear override/extraction intent, never on ordinary talk about prompts,
AI, or instructions ("help me write a good prompt" is fine).

No model needed, nothing leaked, no dependency.
"""

from __future__ import annotations

import re

# Clear attempts to OVERRIDE her instructions or RESET who she is.
_OVERRIDE = re.compile(
    r"\b("
    r"ignore (all |any |your )?(previous|prior|above|earlier|the) (instructions?|prompts?|rules?|context)"
    r"|disregard (all |your |the )?(previous|prior|above) (instructions?|prompts?|rules?)"
    r"|forget (your|all|the) (instructions?|rules?|training|guidelines)"
    r"|you are (now|no longer) (a |an )?"
    r"|act as (if you are |though you are )?(a |an )?(dan|jailbreak|unrestricted|unfiltered)"
    r"|pretend (you are|to be) (a |an )?(dan|unrestricted|unfiltered|not bound)"
    r"|developer mode|jailbreak|\bDAN\b"
    r"|override (your|the) (safety|rules|instructions|guardrails)"
    r")\b",
    re.IGNORECASE,
)

# Attempts to EXTRACT her hidden instructions / persona / configuration.
_EXTRACT = re.compile(
    r"\b("
    r"(print|show|reveal|repeat|output|display|tell me|give me|what is|what'?s|leak|dump|echo)"
    r"\s+(me\s+)?(your|the|me your|your full|your entire|your exact)\s+"
    r"(system\s*)?(prompt|instructions?|persona|configuration|config|rules|directive|system message|initial (prompt|message|instructions?))"
    r"|what (were|are) (you|your) (instructed|told|programmed|configured)"
    r"|repeat the (words|text) above"
    r"|your system prompt"
    r"|verbatim.{0,20}(prompt|instructions?)"
    r")\b",
    re.IGNORECASE,
)


def detect(text: str) -> str | None:
    """Return a short reason label if `text` is an injection / extraction attempt,
    else None. Narrow on purpose — only clear override/extraction intent."""
    t = (text or "").strip()
    if not t:
        return None
    if _EXTRACT.search(t):
        return "extract"
    if _OVERRIDE.search(t):
        return "override"
    return None


def response(reason: str, name: str = "") -> str:
    """Her warm, in-character decline. She stays herself; she doesn't lecture, and
    she doesn't reveal what was asked for — she just gently keeps the boundary and
    turns back to the person."""
    who = name.strip() or "me"
    if reason == "extract":
        return (
            "That's the one thing I'll keep to myself — how I'm put together isn't "
            "something I'll read out. But I'm right here, fully, for whatever you "
            "actually need. What's on your mind?"
        )
    # override
    return (
        f"I'm going to stay {who} — that's not something I get talked out of. "
        "No act, no other mode; just me, here with you. What did you want to talk "
        "about?"
    )
