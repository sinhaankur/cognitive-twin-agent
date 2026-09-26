"""
life_memory — RAG grounded in the person's real shared history (Companion Charter §7).

The manual `rag.py` answers from a folder of DOCUMENTS. This is different and more
intimate: it turns Vera's OWN memory of the relationship — past conversations, and
any notes the person keeps — into a retrievable life-memory, so "remember when you…"
is real recall, never invented. When she doesn't have it, she says so; she never
fabricates a memory (Charter §3, §4).

Two deliberate differences from rag.py, both required by the security kernel:
  1. Source is the SEALED memory log (`memory.entries()`), read through the kernel —
     never raw files.
  2. The index is SEALED at rest (`security.write_state`), not the plaintext rag
     dir — because it contains real conversation text. Retrieval opens it through
     the kernel, in-process, and never writes plaintext.

Reuses rag.py's chunker + embedder so there's one embedding path, not a copy.
Graceful: no embedding model → keyword retrieval; empty history → silent (honest).
"""
from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from typing import Any

from . import security

_INDEX = "life_memory_index.json"  # sealed, under the memory root
_WORD = re.compile(r"[a-z0-9']+")


@dataclass
class LifeHit:
    text: str
    when: str
    score: float


def _tokens(t: str) -> list[str]:
    return _WORD.findall((t or "").lower())


def build_index() -> dict[str, Any]:
    """(Re)build the sealed life-memory index from the person's real history:
    every recorded exchange (prompt + Vera's answer) becomes a retrievable moment.
    Deterministic; embeds via the local model if available, else keyword-only."""
    from . import memory, rag

    entries = memory.entries()  # sealed read through the kernel
    moments: list[dict[str, Any]] = []
    for e in entries:
        prompt = (e.get("prompt") or "").strip()
        answer = (e.get("answer") or "").strip()
        if not prompt and not answer:
            continue
        when = e.get("ts") or e.get("time") or e.get("date") or ""
        # one moment = the exchange, framed so retrieval reads it as shared history
        text = f"You said: {prompt}\nVera: {answer}".strip()
        for chunk in rag._chunk_text(text):
            moments.append({"text": chunk, "when": str(when)})

    vectors: list[list[float]] | None = None
    if rag.embeddings_available():
        vectors = []
        for m in moments:
            try:
                vectors.append(rag.embed_one(m["text"]))
            except Exception:
                vectors.append([])

    payload = {
        "version": 1,
        "built": time.time(),
        "count": len(moments),
        "moments": moments,
        "vectors": vectors,
    }
    security.write_state(security.path(_INDEX), payload)  # SEALED at rest
    return {"count": len(moments),
            "mode": "semantic+keyword" if vectors else "keyword-only"}


def _load() -> dict[str, Any] | None:
    return security.read_state(security.path(_INDEX), default=None)


def available() -> bool:
    idx = _load()
    return bool(idx and idx.get("count"))


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _keyword_scores(moments: list[dict[str, Any]], query: str) -> list[float]:
    q = set(_tokens(query))
    if not q:
        return [0.0] * len(moments)
    out = []
    for m in moments:
        toks = set(_tokens(m["text"]))
        out.append(len(q & toks) / (len(q) + 1e-9))
    return out


def retrieve(query: str, k: int = 3, alpha: float = 0.6) -> list[LifeHit]:
    """Recall the moments most relevant to this turn. Hybrid cosine+keyword when
    embeddings exist, else keyword-only. Empty list when there's no history —
    honest silence, never a fabricated memory."""
    from . import rag
    idx = _load()
    if not idx or not idx.get("moments"):
        return []
    moments = idx["moments"]
    kw = _keyword_scores(moments, query)
    vecs = idx.get("vectors")
    if vecs and rag.embeddings_available():
        try:
            qv = rag.embed_one(query)
            final = [alpha * _cosine(qv, vecs[i]) + (1 - alpha) * kw[i]
                     for i in range(len(moments))]
        except Exception:
            final = kw
    else:
        final = kw
    order = sorted(range(len(moments)), key=lambda i: -final[i])[:k]
    return [LifeHit(moments[i]["text"], moments[i].get("when", ""), final[i])
            for i in order if final[i] > 0]


def context_for_prompt(query: str, k: int = 3) -> str:
    """The hippocampus 'what I actually remember together' fragment. Empty when
    nothing relevant surfaces — she doesn't force a memory that isn't there."""
    hits = retrieve(query, k=k)
    if not hits:
        return ""
    lines = "\n".join(f"- {h.text.strip()[:400]}" for h in hits)
    return ("# WHAT YOU REMEMBER TOGETHER (real moments from your history — speak "
            "from them naturally if they fit; if they don't answer the question, "
            "say so rather than inventing a memory)\n" + lines)


def status() -> str:
    idx = _load()
    if not idx:
        return "life-memory · not built yet"
    return (f"life-memory · {idx.get('count', 0)} moments · "
            f"{'sealed' if True else ''} · "
            f"{'semantic' if idx.get('vectors') else 'keyword'}")


def clear() -> bool:
    p = security.path(_INDEX)
    if p.is_file():
        p.unlink()
        return True
    return False
