"""
brain_flow — compose the brain's organs into ONE ordered flow (Companion Charter §6).

The charter promises behaviour is produced by the anatomy, in order, with the LLM
as the last and smallest step (the mouth), not the mind:

    turn
     → limbic       : feel it            (feel.read / feel.directive)   [no LLM]
     → hippocampus  : recall             (memory + mental_model + RAG)  [no LLM]
     → frontal      : choose stance       (inside feel — posture/lead)   [no LLM]
     → cortex       : phrase it           (the LLM — the only LLM organ)

Those organs already exist (feel.py, memory, mental_model.py, rag.py). Before this,
the loop appended each as a separate, unordered fragment. This module composes them
in the charter's order into one labelled block, so the flow is real + legible + one
place to test — and the model receives the felt state and recall it must write
*within*, never as the source of the feeling.

Pure composition: no new lexicons, no LLM, no I/O beyond what the organs already do.
Every step is fail-soft — a missing organ degrades the flow, never crashes it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# A turn "wants facts" when it asks ABOUT something knowable — a question, or a
# request to recall/explain/find. Emotional or casual turns ('I feel lonely',
# 'good morning') do NOT, so we don't pollute them with reference documents. This
# is the gate that keeps RAG CLEAN: relevant context when it helps, silence when
# it doesn't. Keyword-light + a '?' check — transparent, no model call.
_FACTUAL_CUE = re.compile(
    r"\b(what|which|who|where|when|how|why|explain|tell me about|do you know|"
    r"what'?s|how many|how much|list|show|find|look up|search|define|"
    r"project|projects|built|building|work on|stack|tool|doc|document|"
    r"paper|research|code|repo|feature|the math|how does)\b",
    re.IGNORECASE,
)
# Emotional cues that should NEVER trigger a doc lookup even if a stray cue matches.
_EMOTIONAL_SKIP = re.compile(
    r"\b(i feel|feeling|lonely|sad|tired|overwhelmed|anxious|scared|miss (you|her|him)|"
    r"i'?m (so |really )?(down|low|lost|hurt|struggling)|hold me|just talk|i love)\b",
    re.IGNORECASE,
)


def _wants_facts(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _EMOTIONAL_SKIP.search(t):
        return False
    return ("?" in t) or bool(_FACTUAL_CUE.search(t))


@dataclass
class BrainFlow:
    """The ordered output of one pass through the organs. `blocks` is the
    charter-ordered list of system-prompt fragments; `steps` names which organs
    actually fired (for the /brain-explain readout + tests)."""
    blocks: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)

    def as_prompt(self) -> str:
        return "\n\n".join(b for b in self.blocks if b)


def _limbic(text: str) -> str | None:
    """Feel it — Vera's own felt state + stance (feel.directive already blends the
    frontal posture/lead + tone dial + mirror lean). Returns '' on flat turns."""
    try:
        from . import feel
        d = feel.directive(text)
        return d or None
    except Exception:
        return None


def _hippocampus(text: str) -> str | None:
    """Recall — the unified 'what I remember' step: episodic memory relevant to this
    message + the living mental model of the person + grounded life-memory (RAG).
    One block so the model sees a single, coherent recollection, in her voice."""
    recalled: list[str] = []

    # episodic: memories relevant to THIS message (falls back to habit summary)
    try:
        from . import memory
        try:
            ctx = memory.context_for(text)
        except Exception:
            ctx = memory.summary_for_prompt()
        if ctx:
            recalled.append(ctx)
    except Exception:
        pass

    # the living model of the person (feelings / people / threads)
    try:
        from . import mental_model
        mm = mental_model.context_for_prompt()
        if mm:
            recalled.append(mm)
    except Exception:
        pass

    # life-memory: her real shared history — past conversations (and notes) recalled
    # from the SEALED life index (Charter §7). "remember when you…" made real, or
    # honest silence. Built from memory.entries(); no history → empty.
    try:
        from . import life_memory
        lm = life_memory.context_for_prompt(text)
        if lm:
            recalled.append(lm)
    except Exception:
        pass

    # grounded documents: the manual RAG docs index (rag: index <folder>). Distinct
    # from life-memory — this is reference material, not shared history.
    #
    # ONLY when the turn actually WANTS facts. Injecting reference docs into every
    # turn is why RAG felt bad: 'I feel lonely' pulled a 'scene.tsx refactor plan'
    # (semantic scores compress into a narrow band, so even off-topic chunks score
    # ~0.78). A companion turn needs presence, not documents. We gate on a factual
    # cue + a RELEVANCE FLOOR below, so context is clean and relevant or absent.
    try:
        from . import rag
        indexes = rag.list_indexes() if _wants_facts(text) else []
        if indexes:
            # Search EVERY index, not just "default" — the real knowledge lives in
            # universe-engine / veradocs / veraskills / ue-docs (235+ chunks), and
            # only searching "default" (1 chunk) is why RAG kept missing. Pool the
            # hits across indexes and keep the best by score.
            #
            # Embed the query ONCE and reuse it across every index. Each embed is an
            # Ollama round-trip that contends with the loaded chat model; doing it
            # per-index (several indexes → several embeds) added real latency to
            # EVERY turn. One embed, reused, keeps recall light.
            query_vec = None
            try:
                if rag.embeddings_available():
                    query_vec = rag.embed_one(text)
            except Exception:
                query_vec = None
            pooled: list = []
            for name in indexes:
                try:
                    # Use PLAIN retrieve (vector + keyword), NOT retrieve_reranked:
                    # reranking fires an expand-query + rerank LLM call PER index,
                    # so across several indexes it added ~10 model calls and ~30-60s
                    # to EVERY turn — the reason the chat felt frozen and heavy.
                    # Plain retrieve is near-instant and already scores well; we pool
                    # by score across indexes and keep the top few. (Vera must be a
                    # catalyst, not a tax.)
                    for h in rag.retrieve(text, name=name, k=4, query_vec=query_vec):
                        if getattr(h, "text", "").strip():
                            # tag which index it came from for the citation
                            setattr(h, "_index", name)
                            pooled.append(h)
                except Exception:
                    continue
            pooled.sort(key=lambda h: getattr(h, "score", 0.0), reverse=True)
            # RELEVANCE FLOOR: semantic scores compress into a narrow band, so keep
            # only hits that are BOTH strong in absolute terms AND close to the best
            # hit. An off-topic query — where even the top hit is weak — then yields
            # nothing rather than noise. This is what makes the context clean.
            if pooled:
                best = getattr(pooled[0], "score", 0.0)
                floor = max(0.82, best * 0.97)
                top = [h for h in pooled if getattr(h, "score", 0.0) >= floor][:3]
            else:
                top = []
            snippets = "\n".join(
                f"- [{getattr(h, '_index', 'doc')}] {h.text.strip()[:500]}" for h in top)
            if snippets:
                mode = "semantic+keyword" if rag.embeddings_available() else "keyword-only"
                recalled.append(
                    "From your reference documents (on-device retrieval · "
                    f"{mode}) — use them when relevant; say so if they don't cover "
                    "the question:\n"
                    f"{snippets}")
    except Exception:
        pass

    if not recalled:
        return None
    return "\n\n".join(recalled)


def compose(text: str) -> BrainFlow:
    """Run the organs in charter order and return the composed flow. The caller
    (agent loop) puts `flow.as_prompt()` into the system prompt right after the
    persona — so the cortex (LLM) writes WITHIN the feeling + recall, never as
    their source."""
    flow = BrainFlow()

    # 1 + 3. limbic (feel) with the frontal stance already folded in by feel.py.
    limbic = _limbic(text)
    if limbic:
        flow.blocks.append(limbic)
        flow.steps.append("limbic+frontal")

    # 2. hippocampus (recall): memory + mental model + RAG life-memory.
    hippo = _hippocampus(text)
    if hippo:
        flow.blocks.append(hippo)
        flow.steps.append("hippocampus")

    # 4. cortex is the LLM itself — it runs in the agent loop, phrasing the reply
    #    within the blocks above. Nothing to compose here; we just note the handoff.
    flow.steps.append("cortex(LLM)")
    return flow


def explain(text: str) -> str:
    """A one-line trace of which organs fired for this turn — for transparency
    (/brain-explain) and tests. Honest: names only the organs that actually spoke."""
    flow = compose(text)
    return "brain-flow · " + " → ".join(flow.steps)
