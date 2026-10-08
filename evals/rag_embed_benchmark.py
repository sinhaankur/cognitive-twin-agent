"""
RAG embedder benchmark — find the best on-device embedding model for Vera's
retrieval (her wisdom + life), measured, not guessed.

The question this answers: when someone says "I feel lost and keep second-
guessing," which embedding model most reliably retrieves the RIGHT conviction of
hers? A better embedder = her RAG surfaces the memory/belief that actually fits,
so her reply lands. We measure that on a labelled test set.

Metrics (standard retrieval):
  - hit@1  : fraction of queries whose TOP result is the intended one
  - hit@3  : fraction whose intended result is in the top 3
  - MRR    : mean reciprocal rank (1/rank of the intended result; rewards ranking
             the right thing higher)
  - ms/query : average embedding+search latency (on-device cost)

How it stays honest + on-device:
  - Each candidate embedder is a real Ollama model. If it isn't pulled, it's
    reported as "not available" (pull it to include it) — never faked.
  - The keyword-only baseline (no model) is always measured, so you can see
    exactly how much semantic search actually buys over free text matching.
  - Everything runs locally against the real wisdom corpus.

Run:
    python -m evals.rag_embed_benchmark
    python -m evals.rag_embed_benchmark --models nomic-embed-text,bge-m3
"""
from __future__ import annotations

import argparse
import math
import os
import time
import urllib.request
import json


# ── the labelled test set: query → the conviction it SHOULD retrieve ──────────
# Keyed by a stable snippet of the seed conviction (wisdom._SEED). Each query is a
# real way someone might bring that moment; the gold answer is the belief that
# truly fits. This is the ground truth the embedders are scored against.
GOLD: list[tuple[str, str]] = [
    ("I can't stop worrying about everything that might go wrong", "Worry is interest"),
    ("my mind keeps spiralling about the future", "Worry is interest"),
    ("I'm completely burnt out and running on empty", "Rest isn't the reward"),
    ("I've been pushing too hard and I'm exhausted", "Rest isn't the reward"),
    ("I feel like I have to prove myself to the people I love", "want your presence"),
    ("I'm scared they'll see me when I'm not at my best", "want your presence"),
    ("should I rush this to get it done faster", "done with care"),
    ("I keep cutting corners to move quicker", "done with care"),
    ("I feel completely lost and don't know what to do next", "next kind step"),
    ("I'm stuck and can't see the way forward", "next kind step"),
    ("I keep beating myself up over a mistake", "gentle with yourself"),
    ("I feel so much guilt and shame about failing", "gentle with yourself"),
]

# Candidate on-device embedders, smallest → largest. All run in Ollama.
DEFAULT_MODELS = [
    "nomic-embed-text",        # 274 MB — current default
    "all-minilm",              # ~45 MB — tiny
    "bge-m3",                  # ~1.2 GB — strong multilingual
    "mxbai-embed-large",       # ~670 MB — high quality
    "snowflake-arctic-embed",  # ~670 MB — retrieval-tuned
]

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")


def _tokens(t: str) -> set[str]:
    import re
    return {w for w in re.findall(r"[a-z']+", t.lower()) if len(w) > 2}


def embed(model: str, text: str) -> list[float] | None:
    try:
        req = urllib.request.Request(
            OLLAMA + "/api/embeddings",
            data=json.dumps({"model": model, "prompt": text}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()).get("embedding") or None
    except Exception:
        return None


def model_available(model: str) -> bool:
    return embed(model, "probe") is not None


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def corpus() -> list[str]:
    """The real wisdom convictions (seed set) — what retrieval ranks over."""
    from cognitive_twin import wisdom
    return [s["text"] for s in wisdom._SEED]


def _gold_index(docs: list[str], snippet: str) -> int:
    for i, d in enumerate(docs):
        if snippet.lower() in d.lower():
            return i
    return -1


def score_keyword(docs: list[str]) -> dict:
    """Baseline: no model, pure token overlap. The bar semantics must beat."""
    ranks = []
    t0 = time.time()
    doc_tok = [_tokens(d) for d in docs]
    for q, snip in GOLD:
        gi = _gold_index(docs, snip)
        qt = _tokens(q)
        scored = sorted(
            range(len(docs)),
            key=lambda i: len(qt & doc_tok[i]) / math.sqrt(len(qt) * len(doc_tok[i]) + 1),
            reverse=True,
        )
        ranks.append(scored.index(gi) + 1 if gi in scored else 999)
    return _metrics(ranks, (time.time() - t0) / len(GOLD) * 1000)


def score_model(model: str, docs: list[str]) -> dict | None:
    if not model_available(model):
        return None
    doc_vecs = [embed(model, d) for d in docs]
    if any(v is None for v in doc_vecs):
        return None
    ranks = []
    t0 = time.time()
    for q, snip in GOLD:
        gi = _gold_index(docs, snip)
        qv = embed(model, q)
        if qv is None:
            ranks.append(999)
            continue
        scored = sorted(range(len(docs)), key=lambda i: cosine(qv, doc_vecs[i]), reverse=True)
        ranks.append(scored.index(gi) + 1 if gi in scored else 999)
    return _metrics(ranks, (time.time() - t0) / len(GOLD) * 1000)


def _metrics(ranks: list[int], ms_per_query: float) -> dict:
    n = len(ranks)
    hit1 = sum(1 for r in ranks if r == 1) / n
    hit3 = sum(1 for r in ranks if r <= 3) / n
    mrr = sum(1.0 / r for r in ranks if r < 999) / n
    return {"hit@1": hit1, "hit@3": hit3, "mrr": mrr, "ms": ms_per_query, "n": n}


def run(models: list[str]) -> dict:
    docs = corpus()
    results: dict[str, dict | None] = {"keyword (no model)": score_keyword(docs)}
    for m in models:
        results[m] = score_model(m, docs)
    return results


def _fmt(r: dict | None) -> str:
    if r is None:
        return "  (not pulled — `ollama pull <model>` to include)"
    return (f"  hit@1 {r['hit@1']*100:5.1f}%  |  hit@3 {r['hit@3']*100:5.1f}%  |  "
            f"MRR {r['mrr']:.3f}  |  {r['ms']:5.1f} ms/query")


def main() -> int:
    ap = argparse.ArgumentParser(description="Benchmark RAG embedders for Vera.")
    ap.add_argument("--models", help="comma-separated model ids (default: the candidate set)")
    args = ap.parse_args()
    models = args.models.split(",") if args.models else DEFAULT_MODELS

    print(f"RAG embedder benchmark — {len(GOLD)} queries over Vera's wisdom corpus\n")
    results = run(models)
    # best by hit@1 then MRR, among available
    best, best_key = None, None
    for name, r in results.items():
        print(f"{name}")
        print(_fmt(r))
        if r and (best is None or (r["hit@1"], r["mrr"]) > (best["hit@1"], best["mrr"])):
            best, best_key = r, name
    print()
    if best_key:
        print(f"→ best available: {best_key}  (hit@1 {best['hit@1']*100:.1f}%, MRR {best['mrr']:.3f})")
        kw = results["keyword (no model)"]
        if best_key != "keyword (no model)" and kw:
            lift = (best["hit@1"] - kw["hit@1"]) * 100
            print(f"  semantic lift over keyword-only: {lift:+.1f} pts hit@1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
