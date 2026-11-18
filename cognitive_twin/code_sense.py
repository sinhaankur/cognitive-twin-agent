"""
Code sense — Vera's knowledge of YOUR code and projects.

Part of the "Vera understands everything" vision (docs/VERA-HUB-VISION.md): a local
coding partner, folded INTO Vera rather than a separate app. It reuses Vera's own
RAG (``cognitive_twin.rag``) with a dedicated ``"code"`` index, so there is ONE
retrieval system — no parallel codepartner. Point it at your repos; Vera can then
answer about your actual code, citing the real files.

Local-first + private by construction: embeddings run on the local backend (Ollama
LM Studio), the index is an owner-only JSON sidecar under ~/.cognitive-twin/rag/,
nothing leaves the machine. Opt-in: Vera only knows the code you explicitly index.

CLI:
    ctwin code index                 # (re)build the code index from your repos
    ctwin code ask "how does X work" # one-shot question about your code
"""

from __future__ import annotations

import os
from typing import Any

from . import rag

# The named RAG index this module owns (sibling to Vera's "default" wisdom index).
CODE_INDEX = "code"

# Your repos. Override with CTWIN_CODE_DIRS (colon-separated). We index source dirs,
# not node_modules/.venv — rag._ingest_dir already handles text files only.
_DEFAULT_DIRS = [
    "~/Documents/diwali-bingo/lib",
    "~/Documents/diwali-bingo/app",
    "~/Documents/Portfolio/components",
    "~/Documents/Portfolio/lib",
    "~/Documents/Portfolio/app",
    "~/Documents/cognitive-twin-agent/cognitive_twin",
    "~/Documents/rag-engine/rag",
]


def code_dirs() -> list[str]:
    env = os.environ.get("CTWIN_CODE_DIRS", "").strip()
    raw = env.split(":") if env else _DEFAULT_DIRS
    return [os.path.abspath(os.path.expanduser(d)) for d in raw if d.strip()]


def build(dirs: list[str] | None = None) -> dict[str, Any]:
    """(Re)build the code index from your repos, merged into ONE ``code`` index.

    Code must NOT use rag's prose_first (that keeps only docs); here we WANT the
    source, so prose_first=False. We build each dir then merge the chunks + vectors
    into the single code index so retrieval spans all your projects at once."""
    dirs = dirs or code_dirs()
    all_chunks: list[dict[str, Any]] = []
    all_vectors: list[list[float]] | None = [] if rag.embeddings_available() else None
    indexed: list[str] = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        # build into a scratch name, then read its payload and merge
        scratch = f"_code_part_{abs(hash(d)) % 10_000}"
        info = rag.build_index(d, name=scratch, prose_first=False)
        payload = rag._load_index(scratch)  # internal, same package
        if payload:
            all_chunks.extend(payload.get("chunks", []))
            vecs = payload.get("vectors")
            if all_vectors is not None and vecs:
                all_vectors.extend(vecs)
            indexed.append(d)
        # clean up the scratch index file
        try:
            os.remove(rag._index_path(scratch))
        except OSError:
            pass

    # write the merged single code index using rag's own path + format
    import json
    payload = {
        "version": 1,
        "folder": "+".join(indexed),
        "chunks": all_chunks,
        "vectors": all_vectors,
    }
    with open(rag._index_path(CODE_INDEX), "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return {
        "index": CODE_INDEX,
        "dirs": len(indexed),
        "chunks": len(all_chunks),
        "mode": "semantic+keyword" if all_vectors else "keyword-only",
    }


def retrieve(query: str, k: int = 5) -> list[dict[str, Any]]:
    """Retrieve the most relevant code chunks for a query (citable source + text)."""
    return rag.retrieve(query, name=CODE_INDEX, k=k)


def context_for_prompt(query: str, k: int = 5) -> str:
    """A ready-to-inject block of relevant code for the model's context. Empty
    string when the code index is missing or nothing matches (so callers degrade
    gracefully — Vera just answers without code grounding)."""
    hits = retrieve(query, k=k)
    if not hits:
        return ""
    lines = ["# RELEVANT CODE FROM YOUR PROJECTS (cite the file when you use it)"]
    for h in hits:
        src = h.get("source", "?")
        lines.append(f"\n## {src}\n{h.get('text', '')}")
    return "\n".join(lines)


def is_ready() -> bool:
    """True when a code index exists (so callers know coding sense is available)."""
    return os.path.exists(rag._index_path(CODE_INDEX))
