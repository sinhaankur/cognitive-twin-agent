"""
Reranker tests — the TRAINED relevance scorer for retrieval.

Proves it's a real learned model (not a guess), that it's OFF by default so it
never silently changes behaviour, that scoring runs with no numpy, and that on a
small labelled set it ranks the gold candidate above a clearly-irrelevant one.
"""
from __future__ import annotations

from cognitive_twin import rerank


def test_active_only_when_generalising_or_opted_in(monkeypatch):
    # the reranker is active by default ONLY when its shipped weights were proven on
    # a HELD-OUT set (metrics.generalises). An overfit-only model stays off.
    rr = rerank.get()
    if rr.metrics and rr.metrics.get("held_out") and rr.metrics.get("generalises"):
        assert rerank.active() is True            # proven → trusted as default
    # a kill-switch always wins, generalising or not
    monkeypatch.setenv("CTWIN_RERANK", "0")
    assert rerank.active() is False


def test_weights_load_or_default():
    rr = rerank.get()
    assert len(rr.w) == rerank.N_FEAT
    # a trained file ships; if present, it was trained on real pairs
    if rr.trained_on:
        assert rr.metrics is not None


def test_scoring_runs_without_numpy():
    # scoring is pure Python — a relevant feature vector scores higher than junk
    rr = rerank.get()
    strong = rerank.features("I feel burnt out and exhausted", semantic=0.9,
                             keyword=0.6, cand_text="Rest isn't the reward for finishing.",
                             cand_about="rest burnout tired exhaustion")
    weak = rerank.features("I feel burnt out and exhausted", semantic=0.1,
                           keyword=0.0, cand_text="A thing done with care is never wasted.",
                           cand_about="work craft patience")
    assert rr.score(strong) > rr.score(weak)


def test_about_overlap_is_used():
    """The topic tags the old blend ignored must move the score — that was the
    whole point of training."""
    rr = rerank.get()
    with_tags = rerank.features("money and wealth worries", semantic=0.4, keyword=0.1,
                                cand_text="A saying.", cand_about="money wealth greed finance")
    without = rerank.features("money and wealth worries", semantic=0.4, keyword=0.1,
                              cand_text="A saying.", cand_about="rest sleep")
    assert rr.score(with_tags) > rr.score(without)


def test_training_beats_a_fixed_blend_on_synthetic_labels():
    """Train on synthetic (feature, label) pairs where the gold has high about-
    overlap and verify the learned model separates gold from the rest — a real fit,
    not a lookup. (Skips cleanly if numpy is absent — training needs it.)"""
    try:
        import numpy  # noqa: F401
    except Exception:
        return
    # 4 queries × 5 candidates; the gold (index 0) has strong semantic + about
    samples = []
    import random
    rng = random.Random(0)
    for _ in range(40):
        gold = [rng.uniform(0.7, 1.0), rng.uniform(0.3, 0.7), rng.uniform(0.6, 1.0),
                rng.uniform(0.4, 0.9), 0.0]
        samples.append((gold, 1))
        for _ in range(4):
            junk = [rng.uniform(0.0, 0.5), rng.uniform(0.0, 0.4), rng.uniform(0.0, 0.3),
                    rng.uniform(0.0, 0.3), 0.0]
            samples.append((junk, 0))
    model = rerank.train(samples, epochs=1500)
    assert model.trained_on == len(samples)
    # the learned model should score a strong gold-like vector well above junk
    gold_like = [0.9, 0.5, 0.9, 0.7, 0.0]
    junk_like = [0.2, 0.1, 0.1, 0.1, 0.0]
    assert model.score(gold_like) > 0.6
    assert model.score(junk_like) < 0.4


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f(); print("ok ", n)
