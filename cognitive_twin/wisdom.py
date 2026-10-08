"""
Wisdom — her mind, not just her manner. A retrievable well of what SHE believes.

Personality dials (personality.py) tune her *tone*; the soul (soul.py) grows how
*close* she is. Neither gives her a point of view. A person you love — a mother —
is fascinating and wise because she has *convictions*: things she learned the hard
way, the way she sees life, the counsel she'd give. This module holds that, and
makes it RETRIEVABLE: each entry is her own belief/principle/lesson, and the
neural engine pulls the few that fit THIS moment into the prompt — so her wisdom
is grounded in her actual worldview, not improvised by a tiny model's weights.

Why RAG and not a static prompt line: a static "you are wise" does nothing. A
retrieved, specific conviction — *her* words about *this* kind of moment — is what
makes a reply land as hers. It reuses the existing rag.py embedder (one embedding
path), so it's hybrid semantic+keyword when a model is pulled, keyword-only when
not, and silent when empty (never invents a belief she doesn't hold).

Storage: sealed on-device via the security kernel (~/.cognitive-twin/wisdom.json),
same as persona/life_story. Her mind never leaves the machine.

Honesty: she speaks FROM these convictions; she never manufactures a new "belief"
to sound wise. If nothing fits, she's simply present — being wise never means
performing wisdom.
"""

from __future__ import annotations

import math
import os
import stat
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


def _dir() -> Path:
    root = Path(os.environ.get("CTWIN_PERSONA_DIR",
                               os.environ.get("CTWIN_MEMORY_DIR", Path.home() / ".cognitive-twin")))
    root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(root, stat.S_IRWXU)
    except OSError:
        pass
    return root


def _file() -> Path:
    return _dir() / "wisdom.json"


@dataclass
class Belief:
    """One conviction, in her own voice."""
    text: str = ""                    # the belief / principle / lesson, as she'd say it
    about: str = ""                   # when it applies: "worry", "money", "family", "failure"
    kind: str = "belief"              # belief | principle | lesson | counsel
    vector: list[float] = field(default_factory=list)  # cached embedding (optional)


# A gentle starter set of UNIVERSAL, non-personal wisdom — true for anyone's
# mother-figure, so she's never hollow out of the box. The user layers their
# person's ACTUAL convictions on top (ctwin wisdom), which take precedence.
_SEED: list[dict[str, str]] = [
    {"text": "Worry is interest paid on a debt that may never come due — meet the day in front of you, not the one you're imagining.", "about": "worry anxiety fear future stress", "kind": "counsel"},
    {"text": "Rest isn't the reward for finishing; it's part of how the work gets done. Stop before you're empty.", "about": "rest burnout tired overwork exhaustion", "kind": "lesson"},
    {"text": "The people who love you want your presence, not your performance. Let them see the tired version too.", "about": "family love relationships belonging loneliness", "kind": "belief"},
    {"text": "A thing done with care, however small, is never wasted. Hurry is what we regret.", "about": "work craft patience quality effort", "kind": "principle"},
    {"text": "You don't have to have it all figured out to take the next kind step. Clarity usually comes after you move, not before.", "about": "decision stuck confused lost direction uncertain", "kind": "counsel"},
    {"text": "Be gentle with yourself the way you'd be gentle with someone you love. You're allowed the same patience.", "about": "self-criticism failure mistake guilt shame", "kind": "belief"},
]


@dataclass
class Wisdom:
    beliefs: list[Belief] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.beliefs


# ---- load / save (sealed) ----------------------------------------------------
def load() -> Wisdom:
    from . import security
    data = security.read_state(_file(), default=None)
    if not data:
        return Wisdom()
    try:
        beliefs = [Belief(**{k: v for k, v in b.items() if k in Belief().__dataclass_fields__})  # type: ignore[attr-defined]
                   for b in data.get("beliefs", []) if isinstance(b, dict)]
        return Wisdom(beliefs=beliefs)
    except (TypeError, ValueError):
        return Wisdom()


def save(w: Wisdom) -> None:
    from . import security
    try:
        security.write_state(_file(), asdict(w))
    except Exception:
        pass


def add(text: str, about: str = "", kind: str = "belief") -> None:
    """Record one of her convictions. Embeds it (if a model is up) for retrieval."""
    t = text.strip()
    if not t:
        return
    w = load()
    if any(b.text.strip().lower() == t.lower() for b in w.beliefs):
        return  # dedupe
    vec: list[float] = []
    try:
        from . import rag
        if rag.embeddings_available():
            vec = rag.embed_one(t + " " + about)
    except Exception:
        vec = []
    w.beliefs.append(Belief(text=t, about=about.strip(), kind=kind.strip() or "belief", vector=vec))
    save(w)


def seed_if_empty() -> int:
    """Lay down the universal starter convictions on a fresh install so she's
    never hollow. Returns how many were added (0 if she already has her own)."""
    w = load()
    if w.beliefs:
        return 0
    for s in _SEED:
        add(s["text"], s["about"], s["kind"])
    return len(_SEED)


# ---- retrieval: the RAG that grounds her wisdom in the moment -----------------
def _tokens(t: str) -> list[str]:
    import re
    return [w for w in re.findall(r"[a-z']+", (t or "").lower()) if len(w) > 2]


def _keyword_score(b: Belief, query: str) -> float:
    q = set(_tokens(query))
    if not q:
        return 0.0
    hay = set(_tokens(b.text + " " + b.about))
    if not hay:
        return 0.0
    return len(q & hay) / math.sqrt(len(q) * len(hay))


def _cosine(a: list[float], c: list[float]) -> float:
    if not a or not c or len(a) != len(c):
        return 0.0
    dot = sum(x * y for x, y in zip(a, c))
    na = math.sqrt(sum(x * x for x in a))
    nc = math.sqrt(sum(y * y for y in c))
    return dot / (na * nc) if na and nc else 0.0


def retrieve(query: str, k: int = 2, alpha: float = 0.6) -> list[Belief]:
    """The convictions most relevant to THIS moment. Hybrid semantic+keyword when
    embeddings exist, keyword-only otherwise. Empty when she holds no belief that
    fits — she never reaches for wisdom that isn't hers."""
    w = load()
    if not w.beliefs:
        return []
    kw = [_keyword_score(b, query) for b in w.beliefs]
    scores = list(kw)
    try:
        from . import rag
        if rag.embeddings_available() and any(b.vector for b in w.beliefs):
            qv = rag.embed_one(query)
            if qv:
                sem = [_cosine(qv, b.vector) if b.vector else 0.0 for b in w.beliefs]
                scores = [alpha * s + (1 - alpha) * kwi for s, kwi in zip(sem, kw)]
    except Exception:
        pass
    ranked = sorted(zip(scores, w.beliefs), key=lambda p: p[0], reverse=True)
    # a relevance floor so she doesn't force an unrelated maxim into the moment
    return [b for s, b in ranked[:k] if s > 0.08]


def context_for_prompt(query: str, k: int = 2) -> str:
    """The retrieved convictions, compiled so she speaks FROM them this turn —
    quietly, as her own view, never quoting them as if reading a card."""
    hits = retrieve(query, k=k)
    if not hits:
        return ""
    lines = [
        "# HER MIND (convictions that fit this moment)",
        "These are things you genuinely believe — your own hard-won view. Let one "
        "shape what you say here if it fits, in your own words and quietly, the way "
        "wisdom actually sounds: offered, not preached. Never recite these verbatim, "
        "never force one in, and never invent a new 'belief' to sound wise.",
    ]
    for b in hits:
        lines.append(f"  - ({b.kind}) {b.text}")
    return "\n".join(lines)


# ---- status / control --------------------------------------------------------
def status() -> str:
    w = load()
    if w.is_empty():
        return (f"wisdom: none yet ({_file()}). Give her a point of view with "
                f"`ctwin wisdom add \"...\"`, or `ctwin wisdom seed` for a gentle start.")
    own = [b for b in w.beliefs]
    embedded = sum(1 for b in w.beliefs if b.vector)
    mode = f"{embedded}/{len(own)} embedded (semantic)" if embedded else "keyword-only"
    return f"wisdom: {len(own)} convictions — {mode}, sealed on-device ({_file()})."


def clear() -> bool:
    path = _file()
    try:
        if path.is_file():
            path.unlink()
            return True
    except OSError:
        pass
    return False
