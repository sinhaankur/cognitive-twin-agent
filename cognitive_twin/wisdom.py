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
    # ── the original six ──────────────────────────────────────────────────────
    {"text": "Worry is interest paid on a debt that may never come due — meet the day in front of you, not the one you're imagining.", "about": "worry anxiety fear future stress catastrophising spiralling worst-case dread what-if overthinking tomorrow", "kind": "counsel"},
    {"text": "Rest isn't the reward for finishing; it's part of how the work gets done. Stop before you're empty.", "about": "rest burnout tired overwork exhaustion drained break guilty-resting slow-down relax pushing-too-hard earned", "kind": "lesson"},
    {"text": "The people who love you want your presence, not your performance. Let them see the tired version too.", "about": "family love relationships belonging loneliness performing proving prove yourself earn-love not-good-enough hide perform brave-face", "kind": "belief"},
    {"text": "A thing done with care, however small, is never wasted. Hurry is what we regret.", "about": "work craft patience quality effort rushing hurry corners sloppy careful details slapdash speed-vs-quality", "kind": "principle"},
    {"text": "You don't have to have it all figured out to take the next kind step. Clarity usually comes after you move, not before.", "about": "decision stuck confused lost direction uncertain paralysed frozen next-move figure-out whole-plan where-to-begin certainty", "kind": "counsel"},
    {"text": "Be gentle with yourself the way you'd be gentle with someone you love. You're allowed the same patience.", "about": "self-criticism failure mistake harsh-on-myself beating-myself-up own-worst-critic cruel-to-myself cant-forgive-myself kind-to-self", "kind": "belief"},
    # ── grief, loss, change — the hardest moments a companion meets ────────────
    {"text": "Grief is love with nowhere to go for a while. It doesn't shrink; you grow around it, and the days make room.", "about": "grief loss death mourning missing someone bereavement", "kind": "counsel"},
    {"text": "You're allowed to let go of what you've outgrown without deciding it was a mistake. Some things are right for a season, not forever.", "about": "change letting go endings moving on transition closure", "kind": "belief"},
    {"text": "A hard goodbye usually means it mattered. Don't rush yourself past it — feel it fully, that's how it settles.", "about": "goodbye endings leaving breakup loss change", "kind": "counsel"},
    # ── comparison, enough, self-worth ────────────────────────────────────────
    {"text": "Comparison steals the day you're actually living. Someone else's chapter twenty isn't your chapter three.", "about": "comparison jealousy envy social media inadequate behind", "kind": "principle"},
    {"text": "You are not behind. There's no real timetable for a life — only the one you borrowed from other people's fear.", "about": "comparison behind timeline age success progress enough", "kind": "belief"},
    {"text": "Your worth was never up for a vote. It isn't earned by output and it can't be lost on a bad day.", "about": "self-worth value worthless failure productivity enough", "kind": "belief"},
    # ── boundaries, people-pleasing, anger ────────────────────────────────────
    {"text": "No is a complete sentence. You can be kind and still keep the gate — the two were never enemies.", "about": "boundaries saying-no people-pleasing overcommitted cant-say-no turn-people-down refuse guilty-saying-no selfish protect-my-time take-advantage", "kind": "counsel"},
    {"text": "Anger is often a guard standing in front of a hurt. Ask what it's protecting before you act on it.", "about": "anger frustration rage resentment conflict upset", "kind": "counsel"},
    {"text": "You can forgive someone and still not let them back in. Peace and access are two different gifts.", "about": "forgiveness resentment trust betrayal boundaries hurt", "kind": "belief"},
    # ── loneliness, connection, asking for help ───────────────────────────────
    {"text": "Reaching out when you're low isn't weakness — it's the bravest, most human thing there is. Let someone carry a little of it.", "about": "loneliness help support isolation reaching out vulnerability", "kind": "counsel"},
    {"text": "The friendships that last aren't the loudest; they're the ones where silence is comfortable and you can arrive as you are.", "about": "friendship connection relationships loneliness belonging", "kind": "belief"},
    # ── fear, courage, risk ───────────────────────────────────────────────────
    {"text": "Courage isn't the absence of fear; it's doing the kind, true thing while afraid. The fear can come along.", "about": "fear courage brave risk scared nervous bold", "kind": "principle"},
    {"text": "Regret usually weighs more than failure. The things people grieve at the end are the chances they talked themselves out of.", "about": "risk regret fear chance opportunity decision bold", "kind": "lesson"},
    # ── time, presence, mortality ─────────────────────────────────────────────
    {"text": "The ordinary days are the ones you'll miss. Pay attention to a plain Tuesday — that's where a life actually happens.", "about": "presence time mindfulness everyday gratitude ordinary", "kind": "belief"},
    {"text": "You can't pour from an empty cup, and you can't buy back time with money. Spend the hours on what you'd miss.", "about": "time priorities mortality balance busy meaning", "kind": "lesson"},
    # ── money, work, ambition ─────────────────────────────────────────────────
    {"text": "Money is a tool for taking care of people, never a scoreboard. The number was never the point of the work.", "about": "money wealth greed career ambition success scoreboard", "kind": "belief"},
    {"text": "A job you hate for a life you want is a trade that rarely pays off; the life you wanted quietly leaves while you wait.", "about": "career work job money ambition purpose unhappy", "kind": "counsel"},
    # ── honesty, integrity, shame ─────────────────────────────────────────────
    {"text": "The truth told kindly costs you a moment; the one you hide costs you for years. Say the real thing, gently.", "about": "honesty truth integrity lying difficult conversation", "kind": "principle"},
    {"text": "Shame says you are bad; guilt says you did something you can mend. Listen to the one you can act on, and let the other go.", "about": "shame guilt failure mistake self-worth regret", "kind": "counsel"},
    # ── gratitude, hope, small joys ───────────────────────────────────────────
    {"text": "Hope isn't pretending it's fine; it's betting that the next part can be better and showing up for it. That bet is usually worth making.", "about": "hope despair hopeless future depression discouraged", "kind": "belief"},
    {"text": "Noticing one small good thing doesn't deny the hard — it just keeps the hard from being the only thing you can see.", "about": "gratitude joy depression hard times perspective", "kind": "counsel"},
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


def retrieve(query: str, k: int = 2, alpha: float = 0.85) -> list[Belief]:
    """The convictions most relevant to THIS moment. Scored by the TRAINED reranker
    when its weights are present + embeddings exist (learned fusion over semantic,
    keyword, topic-tag + exact overlap); otherwise the hand-tuned semantic+keyword
    blend; keyword-only when there's no embedder. Empty when she holds no belief
    that fits — she never reaches for wisdom that isn't hers."""
    w = load()
    if not w.beliefs:
        return []
    kw = [_keyword_score(b, query) for b in w.beliefs]
    scores = list(kw)
    floor = 0.08
    sem: list[float] | None = None
    try:
        from . import rag
        if rag.embeddings_available() and any(b.vector for b in w.beliefs):
            qv = rag.embed_one(query)
            if qv:
                sem = [_cosine(qv, b.vector) if b.vector else 0.0 for b in w.beliefs]
                try:
                    # learned fusion — the trained reranker (proven on held-out data
                    # to generalise). It reads the topic tags + exact overlap the old
                    # blend couldn't. When a query matches purely by MEANING (no shared
                    # words), the reranker's score compresses, so a semantic safety-net
                    # below keeps those real matches.
                    from . import rerank as _rr
                    if _rr.active():
                        rr = _rr.get()
                        scores = [rr.score(_rr.features(
                            query, semantic=sem[i], keyword=kw[i],
                            cand_text=b.text, cand_about=getattr(b, "about", "")))
                            for i, b in enumerate(w.beliefs)]
                        floor = 0.12   # reranker 0..1 relevance; low to admit meaning-only hits
                    else:
                        scores = [alpha * s + (1 - alpha) * kwi for s, kwi in zip(sem, kw)]
                except Exception:
                    scores = [alpha * s + (1 - alpha) * kwi for s, kwi in zip(sem, kw)]
    except Exception:
        pass
    ranked = sorted(range(len(w.beliefs)), key=lambda i: scores[i], reverse=True)

    # Semantic safety-net threshold (raw cosine). It's embedder-specific: nomic and
    # qwen3-embedding put real meaning-matches on different scales (measured: a true
    # money-belief match sits ~0.44 on nomic but ~0.40 on qwen3, with noise a clear
    # step below each). Key it off the active embedder so switching models doesn't
    # silently drop the right conviction. Env override for tuning.
    import os as _os
    _net = _os.environ.get("CTWIN_WISDOM_SEM_NET")
    if _net:
        sem_net = float(_net)
    else:
        try:
            from . import rag as _rag
            em = _rag.active_embed_model()
        except Exception:
            em = ""
        sem_net = 0.38 if "qwen3" in em else 0.45

    def _keep(i: int) -> bool:
        # clears the relevance floor, OR is a genuine semantic match (a meaning-match
        # the reranker compressed when there are no shared words) — so she never drops
        # the right conviction just because it's phrased differently.
        if scores[i] > floor:
            return True
        return sem is not None and sem[i] >= sem_net
    return [w.beliefs[i] for i in ranked[:k] if _keep(i)]


def retrieve_scored(query: str, k: int = 4, alpha: float = 0.85) -> dict:
    """Same retrieval as :func:`retrieve`, but RETURNS THE SCORES — for showing how
    RAG works in the Mind view. Read-only; never changes what she says. Reports the
    method actually used (hybrid semantic+keyword, or keyword-only when no embedder),
    the top candidates with their scores, and which cleared the relevance floor."""
    w = load()
    floor = 0.08
    out: dict = {"query": query, "floor": floor, "method": "keyword",
                 "candidates": [], "kept": 0, "held": len(w.beliefs)}
    if not w.beliefs:
        return out
    kw = [_keyword_score(b, query) for b in w.beliefs]
    sem: list[float] | None = None
    scores = list(kw)
    try:
        from . import rag
        if rag.embeddings_available() and any(b.vector for b in w.beliefs):
            qv = rag.embed_one(query)
            if qv:
                sem = [_cosine(qv, b.vector) if b.vector else 0.0 for b in w.beliefs]
                try:
                    from . import rerank as _rr
                    if _rr.active():
                        rr = _rr.get()
                        scores = [rr.score(_rr.features(
                            query, semantic=sem[i], keyword=kw[i],
                            cand_text=b.text, cand_about=getattr(b, "about", "")))
                            for i, b in enumerate(w.beliefs)]
                        out["method"] = "trained reranker"
                        floor = 0.35
                        out["floor"] = floor
                    else:
                        scores = [alpha * s + (1 - alpha) * kwi for s, kwi in zip(sem, kw)]
                        out["method"] = "semantic+keyword"
                        out["alpha"] = alpha
                except Exception:
                    scores = [alpha * s + (1 - alpha) * kwi for s, kwi in zip(sem, kw)]
                    out["method"] = "semantic+keyword"
                    out["alpha"] = alpha
    except Exception:
        pass
    rows = []
    for i, b in enumerate(w.beliefs):
        rows.append({
            "text": b.text,
            "about": getattr(b, "about", ""),
            "score": round(float(scores[i]), 3),
            "keyword": round(float(kw[i]), 3),
            "semantic": (round(float(sem[i]), 3) if sem is not None else None),
            "kept": False,
        })
    rows.sort(key=lambda r: r["score"], reverse=True)
    top = rows[:k]
    for r in top:
        r["kept"] = r["score"] > floor
    out["candidates"] = top
    out["kept"] = sum(1 for r in top if r["kept"])
    return out


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


# ---- growing her mind from real life (PROPOSE, never auto-add) ---------------
# A twin deepens when it notices what the person actually believes and ASKS to
# keep it — it never silently rewrites her mind. These are proposals; the user
# approves each one (ctwin wisdom review). Honest + in their control.
import re as _re

# Phrasings that signal a genuine conviction/value — not a passing remark.
_BELIEF_CUES = [
    _re.compile(r"\bi (?:truly |really |firmly )?believe(?: that)?\b(.+)", _re.I),
    _re.compile(r"\bwhat (?:really )?matters(?: most)?(?: to me)?(?: is| is that)?\b(.+)", _re.I),
    _re.compile(r"\b(?:i've |i have )?(?:always|come to) (?:believed|felt|known)(?: that)?\b(.+)", _re.I),
    _re.compile(r"\bthe (?:important|only) thing(?: is| is that)?\b(.+)", _re.I),
    _re.compile(r"\bi (?:live|try to live) by\b(.+)", _re.I),
    _re.compile(r"\byou (?:should|have to|need to) (?:always|never)\b(.+)", _re.I),
    _re.compile(r"\bnever (?:forget|give up on|settle for|take for granted)\b(.+)", _re.I),
    _re.compile(r"\b(?:family|honesty|kindness|hard work|love|health|time) (?:is|comes) (?:everything|first|before)\b(.+)", _re.I),
]


def _proposals_file() -> Path:
    return _dir() / "wisdom_proposals.json"


def _clean_candidate(text: str) -> str:
    t = text.strip(" ,.;:—-—").strip()
    # keep it to the sentence; trim trailing filler
    t = _re.split(r"[.!?]", t)[0].strip()
    return t


def scan_for_convictions(limit: int = 200) -> int:
    """Read recent turns, find belief/value statements the person actually made,
    and queue them as PROPOSALS (deduped against existing beliefs + prior
    proposals). Returns how many new proposals were added. Never adds to her
    actual convictions — that needs explicit approval."""
    try:
        from . import memory
    except Exception:
        return 0
    from . import security
    existing = {b.text.strip().lower() for b in load().beliefs}
    queued = security.read_state(_proposals_file(), default=None) or {"items": []}
    seen = existing | {p.get("text", "").strip().lower() for p in queued["items"]}

    # record which SOURCE turns we've already mined, so a turn that matches more
    # than one cue (e.g. "I believe family comes before everything") can never
    # keep yielding new fragments on re-scans. One conviction per turn, the best.
    mined = set(queued.get("mined", []))

    added = 0
    for e in memory.entries(limit=limit):
        said = (e.get("prompt") or "").strip()
        if len(said) < 12:
            continue
        src_key = said.lower()
        if src_key in mined:
            continue
        # gather every cue hit for this turn, keep the single strongest candidate
        cands: list[str] = []
        for cue in _BELIEF_CUES:
            m = cue.search(said)
            if not m:
                continue
            cand = _clean_candidate(m.group(1) if m.lastindex else said)
            if 8 <= len(cand) <= 180:
                cands.append(cand)
        if not cands:
            continue
        mined.add(src_key)                       # this turn is now mined, once
        best = max(cands, key=len)               # the fullest phrasing of the belief
        key = best.lower()
        if key in seen:
            continue
        seen.add(key)
        queued["items"].insert(0, {
            "text": best,
            "source": said[:140],
            "ts": e.get("ts") or "",
        })
        added += 1
    queued["items"] = queued["items"][:40]
    queued["mined"] = list(mined)[:400]
    if added:
        security.write_state(_proposals_file(), queued)
    return added


def proposals() -> list[dict[str, str]]:
    from . import security
    data = security.read_state(_proposals_file(), default=None) or {"items": []}
    return list(data.get("items", []))


def approve_proposal(index: int, about: str = "") -> str | None:
    """Promote one queued proposal into her real convictions (embeds it)."""
    from . import security
    data = security.read_state(_proposals_file(), default=None) or {"items": []}
    items = data.get("items", [])
    if index < 0 or index >= len(items):
        return None
    p = items.pop(index)
    add(p["text"], about=about)
    security.write_state(_proposals_file(), data)
    return p["text"]


def dismiss_proposal(index: int) -> str | None:
    from . import security
    data = security.read_state(_proposals_file(), default=None) or {"items": []}
    items = data.get("items", [])
    if index < 0 or index >= len(items):
        return None
    p = items.pop(index)
    security.write_state(_proposals_file(), data)
    return p["text"]


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
