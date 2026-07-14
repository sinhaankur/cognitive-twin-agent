"""
Local, private, secure memory — on-device only.

Everything the twin learns about you stays in a single file under your home
directory, written owner-only (chmod 0600). Nothing is sent anywhere; there is no
network code in this module. You can read it, and you can clear it.

  store:  ~/.cognitive-twin/memory.jsonl   (override with CTWIN_MEMORY_DIR)

Each line is one interaction: timestamp, what you asked, a short gist of the
answer, and the model used. From that log we derive lightweight "patterns" (your
recurring topics and the times of day you tend to ask) so the agent can reason
more like you — without any profiling leaving the machine.
"""

from __future__ import annotations

import json
import math
import os
import re
import stat
import datetime as _dt
from collections import Counter
from pathlib import Path
from typing import Any


def _dir() -> Path:
    root = Path(os.environ.get("CTWIN_MEMORY_DIR", Path.home() / ".cognitive-twin"))
    root.mkdir(parents=True, exist_ok=True)
    # owner-only directory
    try:
        os.chmod(root, stat.S_IRWXU)  # 0700
    except OSError:
        pass
    return root


def _file() -> Path:
    return _dir() / "memory.jsonl"


def _secure(path: Path) -> None:
    """Lock a file down to owner read/write only (0600)."""
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


# ---- write --------------------------------------------------------------------
def record(prompt: str, answer: str, *, model: str | None = None,
           source: str = "cli") -> None:
    """Append one interaction to the local memory log (owner-only)."""
    # type the memory (emotion / task / opinion / knowledge) from the prompt —
    # cheap rule-based classifier, so the landscape can draw memory regions.
    try:
        from . import mem_types
        mtype = mem_types.classify(prompt or "")
    except Exception:
        mtype = "knowledge"
    entry = {
        "ts": _dt.datetime.now().isoformat(timespec="seconds"),
        "prompt": (prompt or "").strip(),
        # store a gist, not the whole answer — keep the log small and less sensitive
        "gist": (answer or "").strip()[:240],
        "type": mtype,
        "model": model,
        "source": source,
    }
    path = _file()
    existed = path.exists()
    line = json.dumps(entry, ensure_ascii=False)
    # seal at rest (vault: device+account key). If the vault is ever
    # unavailable the line stays plaintext — losing a memory would be worse;
    # `ctwin vault status` tells the truth about what's sealed.
    try:
        from . import vault
        line = vault.seal_line(line)
    except Exception:
        pass
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        if not existed:
            _secure(path)
    except OSError:
        pass  # memory is best-effort; never break the agent over it
    # let the day shadow listen for tasks/completions in what was said — cheap
    # rules, dedup-safe, and never allowed to break memory
    try:
        from . import shadow
        shadow.observe(prompt or "")
    except Exception:
        pass


# ---- read ---------------------------------------------------------------------
def entries(limit: int | None = None) -> list[dict[str, Any]]:
    path = _file()
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("ctv1:"):        # sealed at rest — open with the vault
                try:
                    from . import vault
                    line = vault.open_line(line)
                except Exception:
                    continue                    # wrong device/key: unreadable, skip
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return out[-limit:] if limit else out


def recent_prompts(n: int = 8) -> list[str]:
    return [e.get("prompt", "") for e in entries(limit=n) if e.get("prompt")]


# ---- derive lightweight patterns (all local) ---------------------------------
# Words of 3+ letters count as signal (not 4+): "mom", "dad", "tax" are exactly
# the words a personal twin must never be blind to; the stopword list handles
# the generic 3-letter noise (get/got/now/yes/…).
# A broad stopword set so "learned topics" surface real subjects, not filler.
# Covers articles/pronouns/aux verbs, common conversational verbs, and generic
# words that dominate small logs ("thing", "kind", "someone", "want"…).
_STOP = {
    # articles / conjunctions / prepositions
    "the", "a", "an", "and", "or", "but", "if", "so", "as", "of", "to", "in",
    "on", "at", "by", "for", "with", "from", "into", "about", "over", "under",
    "up", "down", "out", "off", "than", "then", "too", "very", "just",
    # pronouns / determiners
    "i", "me", "my", "mine", "we", "us", "our", "you", "your", "yours", "he",
    "him", "his", "she", "her", "it", "its", "they", "them", "their", "this",
    "that", "these", "those", "who", "whom", "which", "what", "some", "any",
    "each", "every", "all", "both", "few", "more", "most", "other", "such",
    "no", "nor", "not", "only", "own", "same", "one", "ones", "someone",
    "something", "anything", "everything", "thing", "things", "stuff",
    # aux / common verbs
    "is", "are", "was", "were", "be", "been", "being", "am", "do", "does",
    "did", "have", "has", "had", "can", "could", "will", "would", "shall",
    "should", "may", "might", "must", "get", "got", "make", "made", "go",
    "goes", "went", "want", "need", "like", "know", "think", "see", "say",
    "said", "give", "tell", "show", "use", "used", "help", "let", "put",
    "take", "find", "come", "look", "feel", "keep", "kind", "sort", "way",
    # question / instruction words
    "how", "why", "when", "where", "whats", "please", "tools", "tool",
    "okay", "ok", "yes", "yeah", "hey", "hi", "hello", "thanks", "thank",
    "now", "today", "here", "there", "again", "also", "really", "maybe",
    "warm", "line", "good", "nice", "much", "many", "lot", "bit", "little",
}


def patterns() -> dict[str, Any]:
    """
    Summarize recurring topics + active hours from the local log.

    Topics favour *recurrence* and *distinctiveness*: words are scored by
    frequency × length (longer words carry more signal), and when there's
    enough history we require a word to appear more than once so a single
    off-hand prompt doesn't become a "learned topic". Small logs fall back to
    single occurrences so the graph still shows something honest early on.
    """
    es = entries()
    if not es:
        return {"count": 0, "topics": [], "active_hours": []}

    words: Counter[str] = Counter()
    hours: Counter[int] = Counter()
    for e in es:
        text = e.get("prompt", "").lower()
        for raw in text.replace("?", " ").replace("/", " ").split():
            w = "".join(c for c in raw if c.isalnum())
            if len(w) >= 3 and not w.isdigit() and w not in _STOP:
                words[w] += 1
        ts = e.get("ts", "")
        try:
            hours[_dt.datetime.fromisoformat(ts).hour] += 1
        except ValueError:
            pass

    # With a reasonable log, keep only words seen at least twice (real recurrence).
    recurring = {w: c for w, c in words.items() if c >= 2}
    pool = recurring if len(recurring) >= 3 else dict(words)
    # score = frequency × sqrt(length) so distinctive multi-syllable words win
    scored = sorted(pool.items(), key=lambda kv: kv[1] * (len(kv[0]) ** 0.5), reverse=True)
    topics = [w for w, _ in scored[:6]]

    return {
        "count": len(es),
        "topics": topics,
        "active_hours": [h for h, _ in hours.most_common(3)],
    }


def summary_for_prompt() -> str:
    """A short, human line the agent can fold into its system prompt so it reasons
    with awareness of your habits — local only, never sent off device."""
    p = patterns()
    if not p["count"]:
        return ""
    bits = []
    if p["topics"]:
        bits.append("recurring interests: " + ", ".join(p["topics"]))
    recent = recent_prompts(3)
    if recent:
        bits.append("recently asked: " + " / ".join(recent))
    return "Context about this user (from local history, private): " + "; ".join(bits) + "."


# ---- episodic date recall ("what happened on July 1?") ------------------------
# A human hippocampus can travel to a day. So can she: if you name a date, the
# episodes from that day surface. Rule-based and transparent — no model call.
_MONTHS = {m[:3]: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}


def _parse_date_query(text: str) -> tuple[_dt.date, _dt.date] | None:
    """Return a (start, end) day range if the text asks about a specific time
    ('what happened on july 1', 'yesterday', '3 days ago', '2026-07-01',
    'last week'); None otherwise."""
    t = (text or "").lower()
    today = _dt.date.today()
    m = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", t)          # ISO
    if m:
        try:
            d = _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return (d, d)
        except ValueError:
            return None
    if "day before yesterday" in t:
        d = today - _dt.timedelta(days=2); return (d, d)
    if "yesterday" in t:
        d = today - _dt.timedelta(days=1); return (d, d)
    # bare "today" is in half of casual speech ("3 tasks today") — only the
    # explicitly backward-looking phrasings mean the day's episodes
    if "earlier today" in t or "so far today" in t:
        return (today, today)
    m = re.search(r"\b(\d+)\s+days?\s+ago\b", t)
    if m:
        d = today - _dt.timedelta(days=int(m.group(1))); return (d, d)
    if "last week" in t:
        return (today - _dt.timedelta(days=13), today - _dt.timedelta(days=7))
    if "this week" in t:
        return (today - _dt.timedelta(days=today.weekday()), today)
    # "july 1", "july 1st", "1 july", "1st of july" — month name validates the
    # match, so ordinary words followed by numbers never trigger a date
    pair = None
    m = re.search(r"\b([a-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", t)
    if m and m.group(1)[:3] in _MONTHS:
        pair = (m.group(1), m.group(2))
    else:
        m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]{3,9})\b", t)
        if m and m.group(2)[:3] in _MONTHS:
            pair = (m.group(2), m.group(1))
    if pair:
        try:
            d = _dt.date(today.year, _MONTHS[pair[0][:3]], int(pair[1]))
            if d > today:                          # "july 1" said in June = last year's
                d = d.replace(year=today.year - 1)
            return (d, d)
        except ValueError:
            return None
    return None


def on_dates(start: _dt.date, end: _dt.date) -> list[dict[str, Any]]:
    """All episodes whose timestamp falls inside [start, end], in time order."""
    out = []
    for e in entries():
        try:
            d = _dt.datetime.fromisoformat(e.get("ts", "")).date()
        except ValueError:
            continue
        if start <= d <= end:
            out.append(e)
    return out


# ---- reconsolidation (memories she actually uses grow stronger) ---------------
# In a human brain, every recall re-writes the memory a little stronger; the
# untouched ones fade in priority (never deleted). Here: a small owner-only
# sidecar counts how often each episode was folded into her real thinking, and
# recall scoring favours the well-worn ones.
def _strength_file() -> Path:
    return _dir() / "strength.json"


def _strengths() -> dict[str, int]:
    try:
        raw = _strength_file().read_bytes()
        if raw.startswith(b"CTV1F"):            # sealed at rest
            from . import vault
            raw = vault.open_bytes(raw)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def _skey(e: dict[str, Any]) -> str:
    return (e.get("ts", "") or "") + "|" + ((e.get("prompt", "") or "")[:60])


def strength_of(e: dict[str, Any]) -> int:
    """How many times this episode has been recalled into real thinking."""
    return _strengths().get(_skey(e), 0)


def reinforce(hits: list[dict[str, Any]]) -> None:
    """Mark these episodes as used-in-thought (reconsolidation). Best-effort."""
    if not hits:
        return
    try:
        counts = _strengths()
        for e in hits:
            k = _skey(e)
            counts[k] = counts.get(k, 0) + 1
        path = _strength_file()
        data = json.dumps(counts).encode("utf-8")
        try:
            from . import vault
            data = vault.seal_bytes(data)
        except Exception:
            pass
        path.write_bytes(data)
        _secure(path)
    except OSError:
        pass


# ---- relevance recall (the "it remembers *you*" bit) --------------------------
def _terms(text: str) -> set[str]:
    """Content words of a string — lowercased, stopwords and short tokens dropped.
    Same filter as patterns() so recall and topics agree on what 'signal' is."""
    out: set[str] = set()
    for raw in (text or "").lower().replace("?", " ").replace("/", " ").split():
        w = "".join(c for c in raw if c.isalnum())
        if len(w) >= 3 and not w.isdigit() and w not in _STOP:
            out.add(w)
    return out


def recall(query: str, k: int = 3) -> list[dict[str, Any]]:
    """Return the ``k`` past interactions most relevant to ``query``.

    Two honest paths, like a human recall:
    - name a date ("what happened on july 1", "yesterday") and you get that
      day's episodes — time-travel first, topic words (if any) rank within it;
    - otherwise, scoring is simple and dependency-free: overlap of content
      words weighted by term length, a light recency nudge, and a
      reconsolidation bonus for memories she has actually used before.
    No embeddings, no model, O(n) over the local log — runs every turn.
    """
    span = _parse_date_query(query)
    q = _terms(query)
    if span:
        day = on_dates(*span)
        if not day:
            return []
        if q:  # "what did we say about mom yesterday" — rank within the day
            def overlap(e: dict[str, Any]) -> float:
                shared = q & (_terms(e.get("prompt", "")) | _terms(e.get("gist", "")))
                return sum(len(w) ** 0.5 for w in shared)
            day.sort(key=overlap, reverse=True)
        return day[:max(k, 6)]      # a day deserves a fuller answer
    if not q:
        return []
    es = entries()
    if not es:
        return []
    strengths = _strengths()
    scored: list[tuple[float, int, dict[str, Any]]] = []
    n = len(es)
    for i, e in enumerate(es):
        mem_terms = _terms(e.get("prompt", "")) | _terms(e.get("gist", ""))
        shared = q & mem_terms
        if not shared:
            continue
        # length-weighted overlap; +small recency nudge (newer entries have
        # higher i); +reconsolidation: the well-worn memories come up easier
        score = (sum(len(w) ** 0.5 for w in shared) + (i / n) * 0.5
                 + math.log1p(strengths.get(_skey(e), 0)) * 0.25)
        scored.append((score, i, e))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [e for _, _, e in scored[:k]]


def context_for(query: str, k: int = 3) -> str:
    """System-prompt context tailored to what the user just said: the most
    relevant past memories first, then the standing habit summary. This is what
    turns 'has a memory file' into 'remembers you' — folded in per turn.

    Falls back to summary_for_prompt() when nothing specific is relevant, so a
    fresh or off-topic message still gets the standing context and never errors.
    """
    hits = recall(query, k=k)
    if not hits:
        return summary_for_prompt()
    reinforce(hits)   # reconsolidation: used-in-thought memories grow stronger
    lines = []
    for e in hits:
        when = (e.get("ts", "") or "")[:10]  # YYYY-MM-DD
        prompt = (e.get("prompt", "") or "").strip()
        gist = (e.get("gist", "") or "").strip()
        snippet = prompt if not gist else f"{prompt} → {gist}"
        lines.append(f"- ({when}) {snippet}"[:220])
    recalled = ("Relevant things you remember about this user (from local, "
                "private history — use naturally, don't recite):\n" + "\n".join(lines))
    standing = summary_for_prompt()
    return recalled + ("\n\n" + standing if standing else "")


# ---- clear --------------------------------------------------------------------
def clear() -> bool:
    """Delete all stored memory (and its strength sidecar). True if removed."""
    removed = False
    for path in (_file(), _strength_file()):
        try:
            if path.is_file():
                path.unlink()
                removed = True
        except OSError:
            pass
    return removed


def status() -> str:
    p = patterns()
    loc = _file()
    if not p["count"]:
        return f"local memory: empty ({loc})"
    return (f"local memory: {p['count']} interactions, "
            f"top topics [{', '.join(p['topics'])}] — private, on-device ({loc})")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "clear":
        print("cleared" if clear() else "nothing to clear")
    else:
        print(status())
