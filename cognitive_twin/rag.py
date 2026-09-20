"""
rag — Vera's on-device Retrieval-Augmented Generation over your own documents.

So the twin can answer "what did the Munger flood letter say?" or "summarise the
Universe Engine data" grounded in real files, with citations — instead of guessing
from the model's head. Point it at a folder; it chunks the files, embeds them with
the SAME local model Vera already uses (Ollama), retrieves the closest passages,
and hands them to Vera's local LLM to answer FROM that context only.

Posture (matches places/music and Vera's sealed, on-device design):
  - ON-DEVICE. Embeddings + generation run on the local Ollama backend; nothing
    leaves the machine.
  - GRACEFUL. No embedding model pulled? Falls back to keyword (TF-IDF) retrieval,
    so it still answers from the real documents rather than failing.
  - CITABLE. Every answer carries the source file + chunk it was built from.
  - BEST-EFFORT. A missing folder / down model never crashes the agent loop.

The index is a plain JSON sidecar under ~/.cognitive-twin/rag/ (owner-only), so it
persists between runs and can be inspected.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import json
import math
import os
import re
import urllib.request
from dataclasses import dataclass

# ---- config: reuse Vera's own local backend --------------------------------
def _ollama_host() -> str:
    return (os.environ.get("CTWIN_OLLAMA_HOST") or "http://localhost:11434").rstrip("/")


def _embed_model() -> str:
    # a dedicated embedding model if pulled; the switch below handles its absence
    return os.environ.get("CTWIN_EMBED_MODEL", "nomic-embed-text")


def _rag_dir() -> str:
    d = os.path.expanduser("~/.cognitive-twin/rag")
    os.makedirs(d, exist_ok=True)
    try:
        os.chmod(os.path.dirname(d), 0o700)
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


TEXT_EXTS = {".txt", ".md", ".markdown", ".rst", ".json", ".csv", ".py", ".ts",
             ".tsx", ".js", ".html", ".yaml", ".yml"}
_WORD = re.compile(r"[a-z0-9]+")
_PARA = re.compile(r"\n\s*\n")


# ---- embeddings via the local backend (with an honest availability switch) --
def _post(url: str, payload: dict, timeout: float = 60.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def embed_one(text: str) -> list[float]:
    text = (text or "").strip()
    if not text:
        return []
    out = _post(_ollama_host() + "/api/embeddings",
                {"model": _embed_model(), "prompt": text})
    return list(out.get("embedding", []))


def embeddings_available() -> bool:
    """True iff the local embedding model answers with a real vector. Decides
    semantic vs keyword retrieval — never a hard failure either way."""
    try:
        return len(embed_one("probe")) > 0
    except Exception:
        return False


# ---- ingest: folder -> citable chunks --------------------------------------
@dataclass
class Chunk:
    source: str
    ordinal: int
    text: str


def _chunk_text(text: str, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    paras = [p.strip() for p in _PARA.split(text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        if len(p) > max_chars:
            if buf:
                chunks.append(buf); buf = ""
            for i in range(0, len(p), max_chars - overlap):
                chunks.append(p[i:i + max_chars])
            continue
        if buf and len(buf) + 2 + len(p) > max_chars:
            chunks.append(buf)
            tail = buf[-overlap:] if overlap else ""
            buf = (tail + "\n\n" + p).strip() if tail else p
        else:
            buf = (buf + "\n\n" + p).strip() if buf else p
    if buf:
        chunks.append(buf)
    return chunks


def _iter_files(root: str):
    skip = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
            "build", "out", "target", ".next"}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in skip]
        for name in fns:
            if os.path.splitext(name)[1].lower() in TEXT_EXTS:
                yield os.path.join(dp, name)


def _ingest_dir(root: str) -> list[Chunk]:
    root = os.path.abspath(os.path.expanduser(root))
    out: list[Chunk] = []
    for path in sorted(_iter_files(root)):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                raw = f.read()
        except OSError:
            continue
        if not raw.strip():
            continue
        rel = os.path.relpath(path, root)
        for i, ch in enumerate(_chunk_text(raw)):
            out.append(Chunk(source=rel, ordinal=i, text=ch))
    return out


# ---- index: build / save / load --------------------------------------------
def _index_path(name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", name)
    return os.path.join(_rag_dir(), safe + ".json")


# Prose extensions retrieve far better than raw source: measured on the Universe
# Engine, 25 prose chunks answered clean+cited where 1,586 code chunks were noisy.
_PROSE_EXTS = {".md", ".markdown", ".rst", ".txt"}


def build_index(folder: str, name: str = "default", prose_first: bool = True) -> dict:
    """Ingest a folder into a saved index. If `prose_first` (default) and the
    folder has a healthy amount of prose (docs), index ONLY the prose — code
    embeds noisily and drowns the docs (measured). Set prose_first=False to index
    everything. Embeds if a local model is available, else keyword-only."""
    chunks = _ingest_dir(folder)
    if prose_first:
        prose = [c for c in chunks if os.path.splitext(c.source)[1].lower() in _PROSE_EXTS]
        # only switch to prose-only when there's meaningful doc coverage AND the
        # folder is code-heavy enough that code would drown it
        if len(prose) >= 5 and len(prose) < len(chunks) * 0.5:
            chunks = prose
    vectors = None
    if embeddings_available():
        vectors = []
        for c in chunks:
            try:
                vectors.append(embed_one(c.text))
            except Exception:
                vectors.append([])
    payload = {
        "version": 1,
        "folder": os.path.abspath(os.path.expanduser(folder)),
        "chunks": [{"source": c.source, "ordinal": c.ordinal, "text": c.text} for c in chunks],
        "vectors": vectors,
    }
    with open(_index_path(name), "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return {"name": name, "chunks": len(chunks),
            "mode": "semantic+keyword" if vectors else "keyword-only",
            "folder": payload["folder"]}


def _load_index(name: str = "default") -> dict | None:
    p = _index_path(name)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def list_indexes() -> list[str]:
    d = _rag_dir()
    return sorted(os.path.splitext(f)[0] for f in os.listdir(d) if f.endswith(".json"))


# ---- retrieve: hybrid cosine + keyword -------------------------------------
def _tokens(t: str) -> list[str]:
    return _WORD.findall((t or "").lower())


def _keyword_scores(chunks: list[dict], query: str) -> list[float]:
    n = len(chunks)
    scores = [0.0] * n
    q = _tokens(query)
    if not q or not n:
        return scores
    df: dict[str, int] = {}
    tfs: list[dict[str, int]] = []
    for ch in chunks:
        counts: dict[str, int] = {}
        for tok in _tokens(ch["text"]):
            counts[tok] = counts.get(tok, 0) + 1
        tfs.append(counts)
        for tok in counts:
            df[tok] = df.get(tok, 0) + 1
    for tok in set(q):
        d = df.get(tok, 0)
        if not d:
            continue
        idf = math.log(1 + n / d)
        for i, counts in enumerate(tfs):
            tf = counts.get(tok, 0)
            if tf:
                scores[i] += (1 + math.log(tf)) * idf
    mx = max(scores) if scores else 0.0
    return [s / mx if mx > 0 else 0.0 for s in scores]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return (dot / (na * nb) + 1.0) / 2.0


@dataclass
class Hit:
    source: str
    ordinal: int
    text: str
    score: float


def retrieve(query: str, name: str = "default", k: int = 4, alpha: float = 0.6) -> list[Hit]:
    idx = _load_index(name)
    if not idx or not idx.get("chunks"):
        return []
    chunks = idx["chunks"]
    kw = _keyword_scores(chunks, query)
    vecs = idx.get("vectors")
    if vecs and embeddings_available():
        try:
            qv = embed_one(query)
            final = [alpha * _cosine(qv, vecs[i]) + (1 - alpha) * kw[i] for i in range(len(chunks))]
        except Exception:
            final = kw
    else:
        final = kw
    order = sorted(range(len(chunks)), key=lambda i: -final[i])[:k]
    return [Hit(chunks[i]["source"], chunks[i]["ordinal"], chunks[i]["text"], final[i])
            for i in order if final[i] > 0]


# ---- rerank: widen the candidate pool, then keep the best few --------------
# Retrieval alone can rank the right passage just outside the top-k (that's the
# planet-data miss we saw). The fix (standard 2026 RAG): fetch a WIDER pool, then
# re-score it against the question with the local LLM and keep the best k. Purely
# additive + graceful — no LLM, or any failure, falls back to the retrieval order.
def rerank(query: str, hits: list[Hit], keep: int = 4) -> list[Hit]:
    if len(hits) <= keep:
        return hits
    listing = "\n".join(f"[{i+1}] {h.text[:240]}" for i, h in enumerate(hits))
    try:
        from .llm.ollama_client import OllamaClient, ChatMessage
        model = os.environ.get("CTWIN_MODEL") or "qwen2.5:3b"
        client = OllamaClient(host=_ollama_host(), model=model)
        reply = client.chat([
            ChatMessage(role="system", content=(
                "You rank passages by how well they answer the question. Return ONLY "
                f"the numbers of the {keep} best passages, comma-separated, best first.")),
            ChatMessage(role="user", content=f"Question: {query}\n\nPassages:\n{listing}\n\nBest {keep} numbers:"),
        ])
        idxs = [int(n) - 1 for n in re.findall(r"\d+", reply.content or "")][:keep]
        picked = [hits[i] for i in idxs if 0 <= i < len(hits)]
        if picked:
            # keep any not-picked as backfill so we always return `keep`
            for h in hits:
                if len(picked) >= keep:
                    break
                if h not in picked:
                    picked.append(h)
            return picked[:keep]
    except Exception:
        pass
    return hits[:keep]


def expand_query(query: str) -> str:
    """Rewrite a natural question into a retrieval-friendly query with likely
    DOMAIN terms, so vocabulary mismatch doesn't hide the right passage. (We saw
    'data sources for the planets' miss the real planet table, which is worded in
    domain terms like AU / axial tilt / J2000 — expanding recovers it.) Returns
    the original query plus keywords; falls back to the raw query if no LLM."""
    try:
        from .llm.ollama_client import OllamaClient, ChatMessage
        model = os.environ.get("CTWIN_MODEL") or "qwen2.5:3b"
        client = OllamaClient(host=_ollama_host(), model=model)
        reply = client.chat([
            ChatMessage(role="system", content=(
                "You expand a search query for retrieval. Output ONLY 4-8 extra "
                "keywords/synonyms/technical terms likely to appear in the target "
                "documents — no sentences, no explanation, space-separated.")),
            ChatMessage(role="user", content=f"Query: {query}\n\nExtra keywords:"),
        ])
        extra = (reply.content or "").strip().replace("\n", " ")
        # keep it a query, not a paragraph
        extra = " ".join(_WORD.findall(extra.lower()))[:200]
        return (query + " " + extra).strip() if extra else query
    except Exception:
        return query


def retrieve_reranked(query: str, name: str = "default", k: int = 4,
                      pool: int = 16, expand: bool = True) -> list[Hit]:
    """The full pipeline: retrieve on the RAW query AND (optionally) an expanded
    query, MERGE both candidate pools, then rerank down to k against the original
    question. Expansion can only ADD recall — it never displaces good raw hits, so
    a poor expansion (a small local model guesses imperfectly) can't regress us.
    Every step is graceful; any failure degrades to plain retrieval."""
    raw = retrieve(query, name=name, k=pool)
    merged: list[Hit] = list(raw)
    if expand:
        eq = expand_query(query)
        if eq != query:
            seen = {(h.source, h.ordinal) for h in merged}
            for h in retrieve(eq, name=name, k=pool):
                if (h.source, h.ordinal) not in seen:
                    merged.append(h); seen.add((h.source, h.ordinal))
    if not merged:
        return []
    return rerank(query, merged, keep=k)  # rerank against the real question


# ---- answer: retrieve -> local LLM -> cited answer -------------------------
_SYSTEM = ("You answer strictly from the provided context. If the answer is not in "
           "the context, say you don't know from these documents. Be concise and "
           "cite the sources you used by their [n] markers.")


def answer(query: str, name: str = "default", k: int = 4) -> str:
    hits = retrieve_reranked(query, name=name, k=k)
    if not hits:
        avail = list_indexes()
        if not avail:
            return ("No document index yet. Build one first (rag_index) — point it at "
                    "a folder of notes/docs.")
        return f"Nothing relevant in '{name}'. Available indexes: {', '.join(avail)}."
    context = "\n\n".join(f"[{i+1}] (source: {h.source}#{h.ordinal})\n{h.text}"
                          for i, h in enumerate(hits))
    sources = "\n".join(f"  [{i+1}] {h.source}#{h.ordinal}" for i, h in enumerate(hits))
    # generate with Vera's local backend; degrade to the top passage if it's down
    try:
        from .llm.ollama_client import OllamaClient, ChatMessage
        model = os.environ.get("CTWIN_MODEL") or "qwen2.5:3b"
        client = OllamaClient(host=_ollama_host(), model=model)
        reply = client.chat([
            ChatMessage(role="system", content=_SYSTEM),
            ChatMessage(role="user", content=f"Context:\n{context}\n\nQuestion: {query}"),
        ])
        text = (reply.content or "").strip()
        if not text:
            return f"(Empty reply — most relevant passage.)\n\n{hits[0].text}\n\nSources:\n{sources}"
        return f"{text}\n\nSources:\n{sources}"
    except Exception:
        return (f"(No local LLM reachable — most relevant passage.)\n\n{hits[0].text}\n\n"
                f"Sources:\n{sources}")
