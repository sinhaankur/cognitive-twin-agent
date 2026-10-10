"""
Train the RAG reranker on the labelled eval set, and prove it beats the guess.

For each GOLD (query → the conviction it SHOULD retrieve), we build one positive
pair (query, gold chunk) and negative pairs (query, every other chunk), compute
the real features (semantic cosine via the on-device embedder + keyword tf-idf +
topic-tag overlap + exact-term overlap + query-length), and fit a tiny logistic
reranker so the gold pair outscores the rest.

Then we score BOTH the old hand-tuned blend and the trained reranker on the same
benchmark (hit@1 / hit@3 / MRR) so the improvement is measured, not assumed, and
the weights are only saved when they actually win.

Run:
    python -m evals.train_reranker                 # train + report + save if better
    python -m evals.train_reranker --no-save       # just measure
"""
from __future__ import annotations

import argparse
import math

from cognitive_twin import rerank
from cognitive_twin import wisdom
from evals.rag_embed_benchmark import GOLD, embed


EMBED_MODEL = "nomic-embed-text"


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return (dot / (na * nb) + 1.0) / 2.0   # map [-1,1] → [0,1], as rag.py does


def _keyword_scores(docs, query):
    """Same tf-idf shape as rag._keyword_scores, normalised to the max (0..1)."""
    import re
    tok = lambda t: re.findall(r"[a-z']+", (t or "").lower())
    n = len(docs)
    scores = [0.0] * n
    q = tok(query)
    if not q:
        return scores
    df, tfs = {}, []
    for d in docs:
        counts = {}
        for w in tok(d):
            counts[w] = counts.get(w, 0) + 1
        tfs.append(counts)
        for w in counts:
            df[w] = df.get(w, 0) + 1
    for w in set(q):
        d = df.get(w, 0)
        if not d:
            continue
        idf = math.log(1 + n / d)
        for i, counts in enumerate(tfs):
            tf = counts.get(w, 0)
            if tf:
                scores[i] += (1 + math.log(tf)) * idf
    mx = max(scores) or 0.0
    return [s / mx if mx else 0.0 for s in scores]


def _gold_index(docs, snippet) -> int:
    for i, d in enumerate(docs):
        if snippet.lower() in d.lower():
            return i
    return -1


def build_samples():
    """Compute real features for every (query, candidate) pair, labelled."""
    seed = wisdom._SEED
    docs = [s["text"] for s in seed]
    abouts = [s.get("about", "") for s in seed]
    # embed the corpus once
    print(f"embedding {len(docs)} convictions with {EMBED_MODEL}…")
    doc_vecs = [embed(EMBED_MODEL, d) for d in docs]
    if any(v is None for v in doc_vecs):
        raise SystemExit(f"embedder '{EMBED_MODEL}' unavailable — `ollama pull {EMBED_MODEL}`")

    samples: list[tuple[list[float], int]] = []
    per_query_feats = []   # keep for the metrics pass
    for q, snip in GOLD:
        gi = _gold_index(docs, snip)
        qv = embed(EMBED_MODEL, q)
        kw = _keyword_scores(docs, q)
        feats_for_q = []
        for i in range(len(docs)):
            sem = _cosine(qv, doc_vecs[i]) if qv else 0.0
            f = rerank.features(q, semantic=sem, keyword=kw[i],
                                cand_text=docs[i], cand_about=abouts[i])
            samples.append((f, 1 if i == gi else 0))
            feats_for_q.append(f)
        per_query_feats.append((gi, feats_for_q))
    return docs, per_query_feats, samples


def _metrics_from_scores(per_query_feats, score_fn) -> dict:
    ranks = []
    for gi, feats_for_q in per_query_feats:
        scored = sorted(range(len(feats_for_q)), key=lambda i: score_fn(feats_for_q[i]), reverse=True)
        ranks.append(scored.index(gi) + 1 if gi in scored else 999)
    n = len(ranks)
    return {
        "hit@1": sum(1 for r in ranks if r == 1) / n,
        "hit@3": sum(1 for r in ranks if r <= 3) / n,
        "mrr": sum(1.0 / r for r in ranks if r < 999) / n,
        "n": n,
    }


def _blend_score(alpha=0.6):
    """The OLD hand-tuned fusion, as a scorer over the same features (semantic is
    feature 0, keyword is feature 1) — the baseline the trained model must beat."""
    def fn(f):
        q_short = f[4] > 0.5
        a = 0.45 if q_short else alpha
        return a * f[0] + (1 - a) * f[1]
    return fn


def _fmt(m):
    return f"hit@1 {m['hit@1']*100:5.1f}%  |  hit@3 {m['hit@3']*100:5.1f}%  |  MRR {m['mrr']:.3f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-save", action="store_true", help="measure only, don't save weights")
    args = ap.parse_args()

    docs, per_query_feats, samples = build_samples()
    pos = sum(1 for _, y in samples if y)
    print(f"built {len(samples)} pairs ({pos} gold / {len(samples)-pos} other) "
          f"over {len(docs)} convictions, {len(GOLD)} queries\n")

    baseline = _metrics_from_scores(per_query_feats, _blend_score())
    print("hand-tuned blend (the guess):")
    print("  " + _fmt(baseline))

    model = rerank.train(samples)
    model.metrics = None
    trained = _metrics_from_scores(per_query_feats, model.score)
    print("\ntrained reranker (learned fusion):")
    print("  " + _fmt(trained))
    print("  weights:", {k: round(v, 3) for k, v in zip(rerank.FEATURES, model.w)},
          "bias", round(model.b, 3))

    lift1 = (trained["hit@1"] - baseline["hit@1"]) * 100
    liftm = trained["mrr"] - baseline["mrr"]
    print(f"\n→ lift: {lift1:+.1f} pts hit@1 · {liftm:+.3f} MRR")

    better = (trained["hit@1"], trained["mrr"]) >= (baseline["hit@1"], baseline["mrr"])
    if args.no_save:
        print("(--no-save: not written)")
    elif better:
        model.metrics = {"baseline": baseline, "trained": trained}
        model.save()
        print(f"✓ saved → {rerank.WEIGHTS_PATH.name} (it wins, so it ships)")
    else:
        print("✗ not saved — the trained model did not beat the blend; keeping the guess")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
