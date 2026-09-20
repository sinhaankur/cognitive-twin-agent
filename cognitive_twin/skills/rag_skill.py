"""
rag_skill — Vera answers from YOUR documents, with citations.

So the twin can ground answers in real files (notes, project docs, the Universe
Engine data) instead of guessing — retrieve the relevant passages and cite them.
On-device: chunk/embed/generate all run on Vera's local backend (see rag.py).
Graceful: no embedding model → keyword retrieval; no LLM → the top passage.

Importing this module registers the skills on the default registry.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

from .base import default_registry as R


@R.add(
    "rag_index",
    "Index a folder of documents so Vera can answer questions from them later. "
    "Give the folder path and an optional short name (default 'default'). "
    "On-device; embeds with the local model if available, else keyword-only.",
    {"type": "object", "properties": {
        "folder": {"type": "string", "description": "path to the folder of documents to index"},
        "name": {"type": "string", "description": "optional name for this index (default 'default')"},
    }, "required": ["folder"]},
)
def rag_index(folder: str, name: str = "default") -> str:
    from .. import rag
    try:
        info = rag.build_index(folder, name=name)
    except Exception as e:  # noqa: BLE001 - report, never crash the loop
        return f"Couldn't index '{folder}': {e}"
    return (f"Indexed {info['chunks']} chunks from {info['folder']} "
            f"as '{info['name']}' ({info['mode']}). Ask me about it anytime.")


@R.add(
    "rag_recall",
    "Answer a question grounded in your indexed documents, with sources. Use this "
    "when the user asks about their own notes/files/projects. Optionally target a "
    "specific index by name. Read-only, on-device.",
    {"type": "object", "properties": {
        "query": {"type": "string", "description": "the question to answer from the documents"},
        "name": {"type": "string", "description": "optional index name (default 'default')"},
    }, "required": ["query"]},
)
def rag_recall(query: str, name: str = "default") -> str:
    from .. import rag
    return rag.answer(query, name=name)


@R.add(
    "rag_list",
    "List the document indexes Vera has built (read-only).",
    {"type": "object", "properties": {}},
)
def rag_list() -> str:
    from .. import rag
    idx = rag.list_indexes()
    return "Indexes: " + ", ".join(idx) if idx else "No document indexes yet. Build one with rag_index."
