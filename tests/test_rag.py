"""Vera RAG: chunking, keyword-only retrieval (no embed model), index round-trip,
grounded answer with citations — all offline (no embed model, no LLM)."""

from __future__ import annotations

import os

from cognitive_twin import rag


def _corpus(root):
    (root / "munger.md").write_text(
        "The Munger farm land at Khesra 725 floods every monsoon. In September 2026 "
        "about five feet of water backed up from the A.N. Nala.\n\n"
        "The fix is a bund plus a one-way flap gate so Ganga backwater stays off the plot."
    )
    (root / "ranchi.md").write_text(
        "The Ranchi property is a title dispute, case OS 69 of 2020. The plateau is high "
        "and well drained, so there is no flooding risk there."
    )


def test_chunk_and_ingest(tmp_path):
    _corpus(tmp_path)
    chunks = rag._ingest_dir(str(tmp_path))
    assert len(chunks) >= 2
    assert any(c.source == "munger.md" for c in chunks)


def test_build_and_retrieve_keyword_only(tmp_path, monkeypatch):
    # force no embeddings → keyword path (works with no model pulled)
    monkeypatch.setattr(rag, "embeddings_available", lambda: False)
    monkeypatch.setattr(rag, "_rag_dir", lambda: str(tmp_path / "idx"))
    os.makedirs(str(tmp_path / "idx"), exist_ok=True)
    _corpus(tmp_path)
    info = rag.build_index(str(tmp_path), name="t")
    assert info["chunks"] >= 2
    assert info["mode"] == "keyword-only"
    hits = rag.retrieve("which property floods?", name="t", k=2)
    assert hits and hits[0].source == "munger.md"


def test_answer_extractive_fallback_no_llm(tmp_path, monkeypatch):
    # no embeddings AND no LLM → still a grounded, cited answer (top passage)
    monkeypatch.setattr(rag, "embeddings_available", lambda: False)
    monkeypatch.setattr(rag, "_rag_dir", lambda: str(tmp_path / "idx"))
    os.makedirs(str(tmp_path / "idx"), exist_ok=True)
    _corpus(tmp_path)
    rag.build_index(str(tmp_path), name="t")

    # simulate no local LLM by pointing the client at a dead host
    monkeypatch.setenv("CTWIN_OLLAMA_HOST", "http://127.0.0.1:1")
    out = rag.answer("tell me about the Munger flooding", name="t")
    assert "Sources:" in out
    assert "munger.md" in out or "Nala" in out


def test_list_and_missing_index(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "_rag_dir", lambda: str(tmp_path / "idx"))
    os.makedirs(str(tmp_path / "idx"), exist_ok=True)
    assert rag.list_indexes() == []
    # answering with no index is graceful, not a crash
    assert "index" in rag.answer("anything", name="nope").lower()


def test_index_records_embed_model(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "_rag_dir", lambda: str(tmp_path / "idx"))
    os.makedirs(str(tmp_path / "idx"), exist_ok=True)
    _corpus(tmp_path)
    # force keyword-only (no embeddings) → no embed_model recorded, not stale
    monkeypatch.setattr(rag, "embeddings_available", lambda: False)
    rag.build_index(str(tmp_path), name="k")
    idx = rag._load_index("k")
    assert idx["embed_model"] is None
    assert rag.index_is_stale("k") is False      # keyword-only can't be stale


def test_index_stale_on_embedder_change(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "_rag_dir", lambda: str(tmp_path / "idx"))
    os.makedirs(str(tmp_path / "idx"), exist_ok=True)
    _corpus(tmp_path)
    # pretend embeddings exist and the index was built by a DIFFERENT model
    monkeypatch.setattr(rag, "embeddings_available", lambda: True)
    monkeypatch.setattr(rag, "embed_one", lambda t, **k: [0.1, 0.2, 0.3])
    monkeypatch.setattr(rag, "active_embed_model", lambda: "model-A")
    rag.build_index(str(tmp_path), name="s")
    assert rag.index_is_stale("s") is False       # same model → fresh
    monkeypatch.setattr(rag, "active_embed_model", lambda: "model-B")
    assert rag.index_is_stale("s") is True         # changed model → must rebuild
