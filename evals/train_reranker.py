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
from evals.rerank_trainset import split as _split


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


def _embed_corpus():
    seed = wisdom._SEED
    docs = [s["text"] for s in seed]
    abouts = [s.get("about", "") for s in seed]
    print(f"embedding {len(docs)} convictions with {EMBED_MODEL}…")
    doc_vecs = [embed(EMBED_MODEL, d) for d in docs]
    if any(v is None for v in doc_vecs):
        raise SystemExit(f"embedder '{EMBED_MODEL}' unavailable — `ollama pull {EMBED_MODEL}`")
    return docs, abouts, doc_vecs


def build_for_queries(query_pairs, docs, abouts, doc_vecs):
    """Compute features for a list of (query, gold_snippet). Returns
    (samples, per_query_feats): samples = [(features, label)] for training;
    per_query_feats = [(gold_index, [features per candidate])] for metrics."""
    samples: list[tuple[list[float], int]] = []
    per_query_feats = []
    for q, snip in query_pairs:
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
    return samples, per_query_feats


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
    ap.add_argument("--legacy", action="store_true",
                    help="train+test on the tiny GOLD set (the old overfit path)")
    args = ap.parse_args()

    docs, abouts, doc_vecs = _embed_corpus()

    if args.legacy:
        train_q = test_q = GOLD
        print("LEGACY: train == test on the 12-query GOLD set (overfit)\n")
    else:
        train_q, test_q = _split()
        print(f"train on {len(train_q)} query phrasings · HELD-OUT test on {len(test_q)} "
              f"the reranker never sees in training\n")

    train_samples, _ = build_for_queries(train_q, docs, abouts, doc_vecs)
    _, test_feats = build_for_queries(test_q, docs, abouts, doc_vecs)
    pos = sum(1 for _, y in train_samples if y)
    print(f"training pairs: {len(train_samples)} ({pos} gold / {len(train_samples)-pos} other)\n")

    # measured on the HELD-OUT test set — the honest number
    baseline = _metrics_from_scores(test_feats, _blend_score())
    print("hand-tuned blend (the guess) — on held-out test:")
    print("  " + _fmt(baseline))

    model = rerank.train(train_samples)
    model.metrics = None
    trained = _metrics_from_scores(test_feats, model.score)
    print("\ntrained reranker (learned fusion) — on held-out test:")
    print("  " + _fmt(trained))
    print("  weights:", {k: round(v, 3) for k, v in zip(rerank.FEATURES, model.w)},
          "bias", round(model.b, 3))

    lift1 = (trained["hit@1"] - baseline["hit@1"]) * 100
    liftm = trained["mrr"] - baseline["mrr"]
    print(f"\n→ held-out lift: {lift1:+.1f} pts hit@1 · {liftm:+.3f} MRR")

    better = (trained["hit@1"], trained["mrr"]) >= (baseline["hit@1"], baseline["mrr"])
    generalises = not args.legacy and better
    if args.no_save:
        print("(--no-save: not written)")
    elif better:
        model.metrics = {"baseline": baseline, "trained": trained,
                         "held_out": not args.legacy, "generalises": generalises}
        model.save()
        note = "wins on HELD-OUT data — it generalises" if generalises else "wins (legacy/overfit)"
        print(f"✓ saved → {rerank.WEIGHTS_PATH.name} ({note})")
        if generalises:
            print("  → it's now safe to make the reranker the DEFAULT (rerank.active()).")
    else:
        print("✗ not saved — the trained model did not beat the blend on held-out; keeping the guess")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
