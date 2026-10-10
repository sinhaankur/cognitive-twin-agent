"""
rerank — a TRAINED relevance scorer for retrieval (learned fusion, on-device).

Vera's RAG fuses semantic similarity with keyword overlap. Until now that fusion
was a hand-guessed dial — `alpha ≈ 0.6`, nudged by query length — plus a fixed
relevance floor. It worked, but the weights were a guess.

This learns them instead. A tiny logistic model scores each (query, candidate)
pair from a handful of honest features, trained on the labelled eval set
(evals.rag_embed_benchmark.GOLD) so the gold passage is pushed above the rest. It
is the same idea as the limbic net in the brain engine: a small, legible model
that replaces a guess with something measured — numpy to train, pure-Python to
run, weights shipped, and the hand-tuned blend kept as the fallback.

Features per (query, candidate), all in 0..1 and all inspectable:
  semantic      cosine(query, candidate) — meaning
  keyword       tf-idf overlap — shared words
  about_overlap query tokens ∩ the candidate's topic tags (was unused before!)
  exact         fraction of query content-words present verbatim
  q_short       1 if the query is terse (≤2 words), else 0 — lets it learn that
                short queries lean on keywords, which the old alpha only guessed

Honesty / robustness, same law as the rest of the engine:
  - numpy only to TRAIN. Scoring is pure Python on the learned weights, so it
    never becomes a dependency.
  - no trained weights, or a degenerate feature set → the caller keeps its
    hand-tuned blend. The reranker only ever *improves on measure*, never a
    silent regression.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

_WORD = re.compile(r"[a-z']+")
_STOP = {
    "the", "and", "for", "you", "your", "with", "that", "this", "have", "was",
    "are", "but", "not", "what", "how", "why", "when", "who", "can", "will",
    "just", "about", "from", "they", "them", "its", "our", "out", "get", "got",
    "i'm", "i", "me", "my", "a", "an", "to", "of", "it", "is", "so", "keep",
}

FEATURES = ["semantic", "keyword", "about_overlap", "exact", "q_short"]
N_FEAT = len(FEATURES)

WEIGHTS_PATH = Path(__file__).with_name("rerank_weights.json")


def _content_tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall((text or "").lower()) if len(w) > 2 and w not in _STOP}


def features(query: str, *, semantic: float, keyword: float,
             cand_text: str, cand_about: str = "") -> list[float]:
    """The feature vector for one (query, candidate) pair. `semantic` and `keyword`
    are the scores the caller already computed (0..1); the rest are derived here so
    the model can learn signals the old blend ignored (notably the topic tags)."""
    qt = _content_tokens(query)
    about_t = _content_tokens(cand_about)
    cand_t = _content_tokens(cand_text)
    about_overlap = (len(qt & about_t) / len(qt)) if qt else 0.0
    exact = (len(qt & cand_t) / len(qt)) if qt else 0.0
    q_short = 1.0 if len([w for w in _WORD.findall((query or "").lower())]) <= 2 else 0.0
    return [
        max(0.0, min(1.0, semantic)),
        max(0.0, min(1.0, keyword)),
        max(0.0, min(1.0, about_overlap)),
        max(0.0, min(1.0, exact)),
        q_short,
    ]


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    z = math.exp(x)
    return z / (1.0 + z)


@dataclass
class Reranker:
    """A trained linear scorer: score = sigmoid(w·features + b). Higher = more
    relevant. Weights live as plain lists so scoring needs nothing but Python."""
    w: list[float]
    b: float
    trained_on: int = 0
    metrics: dict | None = None

    def score(self, feats: Sequence[float]) -> float:
        z = self.b + sum(wi * fi for wi, fi in zip(self.w, feats))
        return _sigmoid(z)

    # -- persistence --------------------------------------------------------
    def save(self, path: Path | str = WEIGHTS_PATH) -> None:
        Path(path).write_text(json.dumps({
            "features": FEATURES, "w": self.w, "b": self.b,
            "trained_on": self.trained_on, "metrics": self.metrics,
        }, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path | str = WEIGHTS_PATH) -> "Reranker | None":
        p = Path(path)
        if not p.is_file():
            return None
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("features") != FEATURES or len(d.get("w", [])) != N_FEAT:
                return None  # schema drift → fall back to the blend, never crash
            return cls(w=[float(x) for x in d["w"]], b=float(d["b"]),
                       trained_on=int(d.get("trained_on", 0)), metrics=d.get("metrics"))
        except Exception:
            return None


# A sensible default so the scorer is useful even before training: weights that
# reproduce the old blend (semantic-leaning) plus a small positive push on the
# topic-tag overlap the blend ignored. Training replaces these with learned ones.
def default_reranker() -> Reranker:
    # order matches FEATURES: semantic, keyword, about_overlap, exact, q_short
    return Reranker(w=[2.4, 1.4, 1.2, 0.8, -0.2], b=-1.6, trained_on=0)


# ── training (numpy; pairwise logistic over the GOLD eval set) ────────────────
def train(samples: list[tuple[list[float], int]], *, epochs: int = 3000,
          lr: float = 0.3, l2: float = 1e-3, seed: int = 7) -> Reranker:
    """Fit weights so gold (label 1) outscores non-gold (label 0). `samples` is a
    list of (features, label). Pointwise logistic regression — simple, legible, and
    enough for five features. Requires numpy (training only)."""
    import numpy as np  # noqa: local import so the module imports without numpy

    rng = np.random.default_rng(seed)
    X = np.asarray([f for f, _ in samples], dtype=float)
    y = np.asarray([lbl for _, lbl in samples], dtype=float)
    n, d = X.shape
    w = rng.normal(0, 0.1, d)
    b = 0.0
    # class weight: far more negatives than positives → upweight the gold pairs
    pos = max(1.0, y.sum())
    neg = max(1.0, n - y.sum())
    cw = np.where(y > 0, neg / pos, 1.0)
    for _ in range(epochs):
        z = X @ w + b
        p = 1.0 / (1.0 + np.exp(-z))
        g = (p - y) * cw
        gw = X.T @ g / n + l2 * w
        gb = g.mean()
        w -= lr * gw
        b -= lr * gb
    return Reranker(w=[float(x) for x in w], b=float(b), trained_on=n)


# ── module-level cached instance (load once) ──────────────────────────────────
_cached: Reranker | None = None
_loaded = False


def get() -> Reranker:
    """The reranker to use: the trained one if present, else the sensible default."""
    global _cached, _loaded
    if not _loaded:
        _cached = Reranker.load() or default_reranker()
        _loaded = True
    return _cached  # type: ignore[return-value]


def is_trained() -> bool:
    return get().trained_on > 0


# ── opt-in gate ───────────────────────────────────────────────────────────────
# The trained reranker measurably beats the hand-tuned blend on the eval set
# (+33 pts hit@1), but that set is tiny and it trained on it — so it is NOT yet
# proven to GENERALISE on a HELD-OUT test set (trained on 42 phrasings, +16.7 pts
# hit@1 on 18 queries it never saw). So it is now ON BY DEFAULT when the shipped
# weights carry that proof (metrics.generalises). A kill-switch stays, and weights
# that were only ever overfit do NOT auto-enable.
import os as _os  # noqa: E402


def _home():
    from . import places as _gate
    return _gate._home()


def enable() -> None:
    (_home() / "rerank.enabled").write_text("1", encoding="utf-8")


def disable() -> None:
    # explicit off switch: a marker file that active() checks first
    (_home() / "rerank.disabled").write_text("1", encoding="utf-8")
    (_home() / "rerank.enabled").unlink(missing_ok=True)


def _generalises() -> bool:
    """True only if the shipped weights were proven on a HELD-OUT set — the honest
    bar for trusting the reranker as the default (not just overfit homework)."""
    m = get().metrics or {}
    return bool(m.get("held_out") and m.get("generalises"))


def active() -> bool:
    """Use the trained reranker this turn? ON BY DEFAULT once the weights are proven
    to generalise (held-out), OR when explicitly opted in. A kill-switch
    (CTWIN_RERANK=0 or rerank.disabled) always wins."""
    if not is_trained():
        return False
    # explicit kill-switch first
    if _os.environ.get("CTWIN_RERANK") in ("0", "false", "no", "off"):
        return False
    try:
        if (_home() / "rerank.disabled").is_file():
            return False
    except Exception:
        pass
    # explicit opt-in
    if _os.environ.get("CTWIN_RERANK") in ("1", "true", "yes"):
        return True
    try:
        if (_home() / "rerank.enabled").is_file():
            return True
    except Exception:
        pass
    # default: on when the shipped weights generalise on held-out data
    return _generalises()
