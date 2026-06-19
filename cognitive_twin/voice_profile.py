"""
Voice profile — let Anita speak the way someone really spoke.

You give her samples of how a person wrote (e.g. your mother's text messages),
and she distils their voice: the warmth, the length, the little expressions and
sign-offs they used. That profile folds into how Anita talks — so she sounds like
*them*, not a generic assistant.

This is deliberately gentle and private. The samples stay on your machine
(``~/.cognitive-twin/voice_samples.txt``), owner-only, and you can remove them at
any time. Nothing is uploaded, ever.

It also holds "custom memory" — facts you explicitly ask her to remember.
"""

from __future__ import annotations

import json
import os
import re
import stat
from collections import Counter
from pathlib import Path
from typing import Any


def _dir() -> Path:
    root = Path(os.environ.get("CTWIN_MEMORY_DIR", Path.home() / ".cognitive-twin"))
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, stat.S_IRWXU)
    except OSError:
        pass
    return root


def _secure(p: Path) -> None:
    try:
        os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass


# --- voice samples (how they wrote) -------------------------------------------
SAMPLES = "voice_samples.txt"
PROFILE = "voice_profile.json"


def add_samples(text: str, *, person: str = "") -> int:
    """Append writing samples (one message per line is ideal). Returns the new
    total sample count."""
    p = _dir() / SAMPLES
    existed = p.exists()
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return _count_samples()
    with p.open("a", encoding="utf-8") as f:
        for ln in lines:
            f.write(ln + "\n")
    if not existed:
        _secure(p)
    if person:
        prof = _read(PROFILE)
        prof["person"] = person
        _write(PROFILE, prof)
    _rebuild_profile()
    return _count_samples()


def _samples() -> list[str]:
    p = _dir() / SAMPLES
    try:
        return [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()] \
            if p.is_file() else []
    except OSError:
        return []


def _count_samples() -> int:
    return len(_samples())


# Warm closings / expressions worth preserving verbatim if they recur.
_ENDEARMENTS = re.compile(
    r"\b(beta|beti|sweetheart|honey|dear|darling|love|my (boy|child|son)|"
    r"take care|god bless|miss you|love you|proud of you)\b", re.IGNORECASE)


def _rebuild_profile() -> dict[str, Any]:
    """Distil the samples into a small style profile."""
    s = _samples()
    prof = _read(PROFILE)
    if not s:
        return prof

    lengths = [len(x.split()) for x in s]
    avg_len = round(sum(lengths) / max(1, len(lengths)))
    text = " ".join(s)

    # recurring endearments / sign-offs, in their own words
    phrases = Counter(m.group(0).lower() for m in _ENDEARMENTS.finditer(text))
    signature = [p for p, _ in phrases.most_common(6)]

    # punctuation warmth signals
    exclaim = text.count("!")
    ellipses = text.count("...") + text.count("…")
    emoji = len(re.findall(r"[\U0001F300-\U0001FAFF❤☀-➿]", text))

    prof.update({
        "samples": len(s),
        "avg_words": avg_len,
        "signature_phrases": signature,
        "warmth": "high" if (exclaim + emoji) > len(s) * 0.5 else "gentle",
        "uses_ellipses": ellipses > len(s) * 0.2,
    })
    _write(PROFILE, prof)
    return prof


def voice_prompt() -> str:
    """A system-prompt block teaching Anita to speak in this person's voice."""
    prof = _read(PROFILE)
    s = _samples()
    if not s:
        return ""
    name = prof.get("person", "")
    lines = ["# HOW TO SPEAK (this person's voice)"]
    if name:
        lines.append(f"Speak the way {name} did — capture their warmth and manner, "
                     f"not a generic assistant tone.")
    if prof.get("avg_words"):
        lines.append(f"They wrote in short messages (~{prof['avg_words']} words); keep it natural and brief.")
    if prof.get("signature_phrases"):
        lines.append("They often said: " + ", ".join(f'"{p}"' for p in prof["signature_phrases"])
                     + " — use these naturally when it fits, never forced.")
    if prof.get("warmth") == "high":
        lines.append("Their tone was warm and expressive.")
    if prof.get("uses_ellipses"):
        lines.append("They sometimes trailed off with … in a gentle way.")
    # a few real examples ground the voice better than any description
    examples = s[-6:]
    if examples:
        lines.append("Examples of how they actually wrote:")
        lines.extend(f"  - {e}" for e in examples)
    lines.append("Echo this voice with love and respect. Never claim to literally "
                 "be them; you carry their warmth forward.")
    return "\n".join(lines)


# --- custom memory (facts you teach her) --------------------------------------
CUSTOM = "custom_memory.json"


def remember(fact: str) -> int:
    """Store a fact the user explicitly asked Anita to remember."""
    data = _read(CUSTOM)
    items = data.get("items", [])
    fact = (fact or "").strip()
    if fact and fact not in items:
        items.append(fact)
    data["items"] = items
    _write(CUSTOM, data)
    return len(items)


def custom_facts() -> list[str]:
    return _read(CUSTOM).get("items", [])


def forget(index: int) -> bool:
    data = _read(CUSTOM)
    items = data.get("items", [])
    if 0 <= index < len(items):
        items.pop(index)
        data["items"] = items
        _write(CUSTOM, data)
        return True
    return False


def custom_prompt() -> str:
    facts = custom_facts()
    if not facts:
        return ""
    return "# WHAT YOU KNOW (the user told you to remember)\n" + \
        "\n".join(f"- {f}" for f in facts)


# --- shared json helpers -------------------------------------------------------
def _read(name: str) -> dict[str, Any]:
    p = _dir() / name
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write(name: str, data: dict[str, Any]) -> None:
    p = _dir() / name
    existed = p.exists()
    try:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if not existed:
            _secure(p)
    except OSError:
        pass


def clear_voice() -> bool:
    removed = False
    for name in (SAMPLES, PROFILE):
        p = _dir() / name
        try:
            if p.is_file():
                p.unlink(); removed = True
        except OSError:
            pass
    return removed


def status() -> str:
    s = _count_samples()
    facts = len(custom_facts())
    prof = _read(PROFILE)
    parts = []
    if s:
        who = prof.get("person", "someone")
        parts.append(f"voice of {who}: {s} samples learned")
    if facts:
        parts.append(f"{facts} custom memories")
    return ("; ".join(parts) + " — on-device") if parts else "no voice profile or custom memories yet"


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "add":
        # ctwin-voiceprofile add "Person Name" < samples piped in or as a file path
        person = sys.argv[2]
        data = ""
        if len(sys.argv) > 3 and Path(sys.argv[3]).is_file():
            data = Path(sys.argv[3]).read_text(encoding="utf-8")
        else:
            data = sys.stdin.read()
        n = add_samples(data, person=person)
        print(f"learned {n} samples of {person}'s voice.")
        print(voice_prompt()[:400])
    elif len(sys.argv) > 1 and sys.argv[1] == "clear":
        print("cleared." if clear_voice() else "nothing to clear.")
    else:
        print(status())
