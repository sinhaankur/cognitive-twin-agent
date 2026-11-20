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

# conviction snippet -> many real query phrasings for it. Keyed by a DISTINCTIVE
# snippet of each wisdom._SEED belief (so the scoring harness can find the gold doc).
# Covers ALL of the grown corpus (27 convictions) — when the corpus grew 6→27, the
# reranker still trained only on the first 6, so the 21 new beliefs were untrained
# distractors and held-out quality cratered (11% → fixed here). Each conviction gets
# ~6 realistic, meaning-first phrasings.
QUERIES: dict[str, list[str]] = {
    "Worry is interest": [
        "I can't stop worrying about everything that might go wrong",
        "my mind keeps spiralling about the future",
        "I keep imagining the worst case over and over",
        "what if it all falls apart, I can't stop thinking it",
        "I'm catastrophising again and I know it",
        "the uncertainty about tomorrow is eating me alive",
    ],
    "Rest isn't the reward": [
        "I'm completely burnt out and running on empty",
        "I've been pushing too hard and I'm exhausted",
        "I'm so tired but I feel guilty resting",
        "I can't stop, there's always more to do",
        "I haven't earned a break yet so I keep going",
        "I'm running myself into the ground",
    ],
    "want your presence": [
        "I feel like I have to prove myself to the people I love",
        "I'm scared they'll see me when I'm not at my best",
        "I feel like I have to perform to be loved",
        "I hide the tired version of myself from my family",
        "I'm worried they'll love me less if I'm weak",
        "I only feel wanted when I'm succeeding for them",
    ],
    "done with care": [
        "should I rush this to get it done faster",
        "I keep cutting corners to move quicker",
        "is it okay to do a sloppy job just to finish",
        "I feel pressure to churn things out fast",
        "quality or speed, I keep picking speed and regretting it",
        "is careful work even worth it when I'm this busy",
    ],
    "next kind step": [
        "I feel completely lost and don't know what to do next",
        "I'm stuck and can't see the way forward",
        "I need the whole plan before I can start and I don't have it",
        "I'm frozen because nothing is certain",
        "I can't move until I know it'll work out",
        "I'm confused about what to even do first",
    ],
    "gentle with yourself": [
        "I keep beating myself up over a mistake",
        "I'm being really hard on myself",
        "I can't forgive myself for messing up",
        "I'm my own worst critic right now",
        "I hate myself for getting it wrong",
        "I'd give a friend grace but never myself",
    ],
    # ── grief / change / goodbye ──────────────────────────────────────────────
    "Grief is love with nowhere": [
        "I'm devastated, someone I love died",
        "the grief comes in waves and knocks me down",
        "I miss them so much it physically hurts",
        "how do I live with this loss",
        "the mourning isn't getting any smaller",
        "I don't know how to carry losing them",
    ],
    "let go of what you've outgrown": [
        "I've outgrown this and I don't know how to move on",
        "is it okay to walk away from something that was once right",
        "I feel guilty leaving a chapter behind",
        "this part of my life feels finished but I'm scared to end it",
        "how do I let go without calling it a mistake",
        "I've changed and it no longer fits me",
    ],
    "hard goodbye usually means it mattered": [
        "saying goodbye is tearing me apart",
        "this breakup is breaking me",
        "leaving this behind hurts so much",
        "why does this ending feel so heavy",
        "I can't stop crying over this parting",
        "the goodbye is harder than I expected",
    ],
    # ── comparison / enough / worth ───────────────────────────────────────────
    "Comparison steals the day": [
        "everyone on social media seems so far ahead of me",
        "I keep comparing myself to other people",
        "I'm so jealous of where my friends are in life",
        "their success makes me feel like nothing",
        "I can't stop measuring myself against others",
        "scrolling makes me feel inadequate",
    ],
    "You are not behind": [
        "I feel like I'm so behind everyone my age",
        "I haven't hit the milestones I should have by now",
        "I'm running out of time to make something of myself",
        "I'm too old to be starting over",
        "everyone else figured life out and I didn't",
        "I feel like a failure for not being further along",
    ],
    "Your worth was never up for a vote": [
        "I feel worthless when I'm not productive",
        "I'm only valuable if I'm achieving something",
        "a bad day makes me feel like I'm nothing",
        "I have to earn the right to exist",
        "my value feels tied to what I produce",
        "I feel like I don't matter unless I'm useful",
    ],
    # ── boundaries / anger / forgiveness ──────────────────────────────────────
    "No is a complete sentence": [
        "I can't say no without feeling guilty",
        "I always overcommit because I can't turn people down",
        "how do I set a boundary without being mean",
        "I keep saying yes when I want to say no",
        "people take advantage because I never refuse",
        "I feel selfish for protecting my own time",
    ],
    "Anger is often a guard": [
        "I'm so angry and I don't know what to do with it",
        "I keep snapping at everyone and I hate it",
        "this rage is consuming me",
        "why am I so furious lately",
        "I feel resentment I can't shake",
        "I lost my temper again and I feel awful",
    ],
    "forgive someone and still not let them": [
        "can I forgive someone but still keep my distance",
        "they hurt me and I don't want them back in my life",
        "do I have to reconcile to forgive",
        "I want peace but I don't trust them again",
        "how do I forgive without letting them hurt me again",
        "letting go of the grudge doesn't mean letting them back",
    ],
    # ── loneliness / friendship ───────────────────────────────────────────────
    "Reaching out when you're low": [
        "I'm struggling but I don't want to burden anyone",
        "asking for help feels like weakness",
        "I feel so alone but I can't reach out",
        "I don't want to be a burden to my friends",
        "it's hard to admit I need support",
        "should I tell someone how low I feel",
    ],
    "friendships that last aren't the loudest": [
        "I feel lonely even around lots of people",
        "my friendships feel shallow and performative",
        "I miss having someone I can just be myself with",
        "what makes a real friendship last",
        "I want deeper connection, not more acquaintances",
        "I feel like no one really knows me",
    ],
    # ── courage / regret ──────────────────────────────────────────────────────
    "Courage isn't the absence of fear": [
        "I'm too scared to do the thing I know I should",
        "fear is stopping me from going for it",
        "how do I be brave when I'm terrified",
        "I want to be bold but I'm frightened",
        "the nerves are talking me out of it",
        "can I act even though I'm afraid",
    ],
    "Regret usually weighs more than failure": [
        "I'm scared to take the chance in case I fail",
        "should I risk it or play it safe",
        "I keep talking myself out of opportunities",
        "I'm afraid I'll regret not trying",
        "is the safe choice worth it if I'll always wonder",
        "I don't want to look back wishing I'd tried",
    ],
    # ── time / presence / mortality ───────────────────────────────────────────
    "ordinary days are the ones you'll miss": [
        "I rush through my days without really living them",
        "I'm always waiting for the big moments",
        "how do I appreciate everyday life more",
        "the normal days feel like they don't count",
        "I want to be more present in small moments",
        "I keep missing the ordinary beauty of my life",
    ],
    "can't pour from an empty cup": [
        "I'm spreading myself too thin across everything",
        "I never have time for what actually matters",
        "I'm so busy but none of it feels meaningful",
        "how do I spend my time on the right things",
        "I keep trading my hours for the wrong stuff",
        "I'm exhausted and still not doing what matters",
    ],
    # ── money / work ──────────────────────────────────────────────────────────
    "Money is a tool for taking care": [
        "should I take the higher-paying job I'll hate",
        "I feel like money is the only measure of success",
        "I'm chasing a bigger number and losing myself",
        "is more money worth being miserable",
        "I treat my salary like a scoreboard",
        "I keep ranking myself by what I earn",
    ],
    "job you hate for a life you want": [
        "I'm stuck in a career I can't stand",
        "I hate my job but I'm scared to leave",
        "is it worth staying somewhere miserable for the pay",
        "my work is draining the life I wanted out of me",
        "should I keep grinding at something I hate",
        "the job pays well but it's making me unhappy",
    ],
    # ── honesty / shame ───────────────────────────────────────────────────────
    "truth told kindly costs you a moment": [
        "I'm avoiding a hard conversation I need to have",
        "should I tell them the truth even if it hurts",
        "I keep hiding something to avoid conflict",
        "how do I be honest without being cruel",
        "I'm scared to say the real thing",
        "is it better to lie to keep the peace",
    ],
    "Shame says you are bad": [
        "I feel like I'm a terrible person for what I did",
        "I'm drowning in shame over a mistake",
        "I can't tell if I did a bad thing or I am bad",
        "the shame makes me want to hide forever",
        "how do I move past feeling worthless over this",
        "I feel broken because of what happened",
    ],
    # ── hope / gratitude ──────────────────────────────────────────────────────
    "Hope isn't pretending it's fine": [
        "I've lost all hope that things can get better",
        "I feel hopeless about the future",
        "how do I believe the next part can improve",
        "I'm so discouraged I can't see a way up",
        "everything feels pointless right now",
        "I don't know how to hope anymore",
    ],
    "Noticing one small good thing": [
        "everything is so hard I can't see any good",
        "how do I find gratitude when life is heavy",
        "the bad stuff is all I can focus on",
        "is it fake to look for small good things when I'm low",
        "I want to notice something good without denying the pain",
        "the hard times blot out everything else",
    ],
}

# how many phrasings per conviction go to TRAIN; the rest are held-out TEST.
# 6 per belief → 4 train / 2 held-out, across all 27 convictions.
TRAIN_PER = 4


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
