"""
Labelled training data for the RAG reranker — enough, and split, to TRAIN it for
real (not just prove the idea on a handful of queries).

Each conviction in wisdom._SEED gets many different ways a real person might bring
that moment. We split them: most phrasings TRAIN the reranker, the rest are a
HELD-OUT test it never sees in training. A win on the held-out set is the honest
signal that it generalises — which is what the earlier overfit caveat was waiting
for before the reranker could be trusted as the default.

Keyed by a stable snippet of the gold conviction (matches wisdom._SEED), exactly
like evals.rag_embed_benchmark.GOLD, so the same scoring harness works.
"""
from __future__ import annotations

# conviction snippet -> many real query phrasings for it
QUERIES: dict[str, list[str]] = {
    "Worry is interest": [
        "I can't stop worrying about everything that might go wrong",
        "my mind keeps spiralling about the future",
        "I'm so anxious about what's coming",
        "I keep imagining the worst case over and over",
        "my head won't stop racing about tomorrow",
        "I'm scared about everything that could happen",
        "I feel this constant dread about the future",
        "what if it all falls apart, I can't stop thinking it",
        "I'm catastrophising again and I know it",
        "the uncertainty is eating me alive",
    ],
    "Rest isn't the reward": [
        "I'm completely burnt out and running on empty",
        "I've been pushing too hard and I'm exhausted",
        "I have nothing left in the tank",
        "I'm so tired but I feel guilty resting",
        "I keep working even though I'm drained",
        "I can't stop, there's always more to do",
        "I'm exhausted but I haven't earned a break",
        "I'm running myself into the ground",
        "I feel bad whenever I try to relax",
        "I'm wiped out and still going",
    ],
    "want your presence": [
        "I feel like I have to prove myself to the people I love",
        "I'm scared they'll see me when I'm not at my best",
        "I don't want my family to see me struggling",
        "I feel like I have to perform to be loved",
        "I'm afraid I'm not good enough for the people close to me",
        "I hide the tired version of myself from them",
        "I feel I have to earn my place with my family",
        "I'm worried they'll love me less if I'm weak",
        "I put on a brave face for the people I care about",
        "I feel like I'm only wanted when I'm succeeding",
    ],
    "done with care": [
        "should I rush this to get it done faster",
        "I keep cutting corners to move quicker",
        "is it okay to do a sloppy job just to finish",
        "I'm tempted to just slap this together",
        "I don't have time to do this properly",
        "should I just hurry through it",
        "I feel pressure to churn things out fast",
        "quality or speed, I keep picking speed and regretting it",
        "I'm rushing everything lately",
        "is careful work even worth it when I'm this busy",
    ],
    "next kind step": [
        "I feel completely lost and don't know what to do next",
        "I'm stuck and can't see the way forward",
        "I have no idea what my next move should be",
        "everything's unclear and I can't decide",
        "I don't know which direction to go",
        "I feel paralysed, I can't figure it out",
        "I need the whole plan before I can start and I don't have it",
        "I'm frozen because nothing is certain",
        "I can't move until I know it'll work",
        "I'm confused about what to even do first",
    ],
    "gentle with yourself": [
        "I keep beating myself up over a mistake",
        "I feel so much guilt and shame about failing",
        "I'm being really hard on myself",
        "I can't forgive myself for messing up",
        "I feel like a failure and I can't shake it",
        "I keep replaying everything I did wrong",
        "I'm my own worst critic right now",
        "I hate myself for getting it wrong",
        "I can't stop punishing myself over this",
        "I feel awful about letting people down",
    ],
}

# how many phrasings per conviction go to TRAIN; the rest are held-out TEST.
TRAIN_PER = 7


def split() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return (train, test) as lists of (query, gold_snippet). Deterministic: the
    first TRAIN_PER phrasings train, the rest test — so TEST queries are never seen
    in training and a win there means real generalisation."""
    train: list[tuple[str, str]] = []
    test: list[tuple[str, str]] = []
    for snippet, qs in QUERIES.items():
        for i, q in enumerate(qs):
            (train if i < TRAIN_PER else test).append((q, snippet))
    return train, test
