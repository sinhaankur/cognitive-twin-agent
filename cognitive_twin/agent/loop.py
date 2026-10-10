"""
The agent loop — the part that was missing in v1.

Wires the local model (Ollama) to the skill registry: load the persona (Layer A),
send the conversation + tool specs to the model, execute any tool calls it makes
(Layer B), feed results back, and iterate until the model answers or we hit the
step bound (a deterministic guardrail — Layer C's first line of defense).

The model client is injected, so the loop is unit-testable with a mock (no live
Ollama needed to prove the plumbing).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..llm.ollama_client import ChatMessage
from ..skills.base import SkillRegistry, default_registry
from .router import RouteDecision, Router
from .. import memory as _memory
from .. import persona as _persona


class ModelClient(Protocol):
    def chat(self, messages: list[ChatMessage], tools: list[dict[str, Any]] | None = None) -> ChatMessage: ...


@dataclass
class AgentResult:
    answer: str
    steps: int
    tool_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    # which model the router picked for this run (None when routing is off).
    # Also carries a permission Decision on an approval pause — both are metadata.
    route: Any = None
    # when the loop paused for approval: the (skill, args) awaiting a yes. The UI
    # re-issues this call with args["_approved"]=True once the user confirms.
    pending: tuple[str, dict[str, Any]] | None = None


def _load_persona() -> str:
    """Vera's core DNA = system_dna.md. Searched across a ROBUST set of paths so
    she never silently drops to the bland default just because she was launched
    from a different working directory (that was the 'Vera keeps going back to
    basic' bug — the persona file wasn't found from a scheduler / other cwd).

    Precedence: CTWIN_SYSTEM_DNA env → repo root (relative to this module) → cwd
    → the user's config dir. If NONE is found we fall back, but LOUDLY (stderr +
    a marker) rather than quietly becoming a generic assistant.
    """
    import os
    import sys

    candidates = []
    env = os.environ.get("CTWIN_SYSTEM_DNA")
    if env:
        candidates.append(Path(env).expanduser())
    # Module-relative repo root — stable regardless of cwd.
    candidates.append(Path(__file__).resolve().parents[2] / "system_dna.md")
    candidates.append(Path.cwd() / "system_dna.md")
    # User config dir (where a customized DNA could live).
    cfg = Path(os.environ.get("CTWIN_PERSONA_DIR", Path.home() / ".cognitive-twin"))
    candidates.append(cfg / "system_dna.md")

    for candidate in candidates:
        try:
            if candidate.is_file():
                text = candidate.read_text(encoding="utf-8").strip()
                if text:
                    return text
        except OSError:
            pass

    # Loud fallback — this should be rare; make it visible so "basic Vera" is
    # never a silent surprise.
    print(
        "[cognitive-twin] WARNING: system_dna.md not found — running with the "
        "GENERIC persona. Set CTWIN_SYSTEM_DNA or run from the repo root.",
        file=sys.stderr,
    )
    return (
        "You are a local-first personal AI agent — pragmatic, concise, no fluff. "
        "Use the provided tools when they help; otherwise answer directly."
    )


class Agent:
    def __init__(
        self,
        client: ModelClient,
        registry: SkillRegistry | None = None,
        max_steps: int = 6,
        persona: str | None = None,
        router: Router | None = None,
        use_memory: bool = False,
    ) -> None:
        self.client = client
        self.registry = registry or default_registry
        self.max_steps = max_steps
        self.persona = persona if persona is not None else _load_persona()
        # Optional policy-driven model router. When set, each run picks a local
        # model per the routing policy and applies it to the client. Left None in
        # tests so the scripted/mock client is used as-is.
        self.router = router
        # Local, private memory: fold the user's habits into the persona so the
        # twin reasons more like them, and record interactions. Off in tests.
        self.use_memory = use_memory
        # Short-term conversation context (this session only, in memory) so
        # follow-ups work: "what's the date?" → "and tomorrow?". Capped.
        self.history: list[ChatMessage] = []
        self.history_turns = 6   # keep the last N user+assistant messages

    def reset_conversation(self) -> None:
        """Forget the current session's back-and-forth (not the on-disk memory)."""
        self.history = []

    def _audit_tool(self, name: str, args: dict[str, Any], decision: str) -> None:
        """Sealed audit of every tool the agent ran, asked about, or was blocked
        on — so you can always see exactly what Vera did on your behalf."""
        try:
            from .. import security
            import time as _t
            safe_args = {k: v for k, v in (args or {}).items() if k != "_approved"}
            security.append_line(
                security.path("agent_audit.jsonl"),
                {"at": _t.time(), "tool": name, "decision": decision, "args": safe_args},
            )
        except Exception:
            pass  # audit must never break the loop

    def run(self, user_input: str, *, record: bool = True,
            on_delta: Any = None) -> AgentResult:
        """``record=False`` answers without writing to memory — for scripted,
        internal prompts (greetings, background reflections). The twin should
        learn from the USER, never from its own boilerplate."""
        # DIDN'T CATCH IT — a blank or noise-only turn (a mic mishearing, a stray
        # sound) should never run the model or become a command. She says so, warmly,
        # instead of answering a phantom. (Only on real user turns, not internal.)
        if record:
            _clean = (user_input or "").strip()
            if len(_clean) < 2 or _clean.lower().strip(" .!,") in {
                "you", "thank you", "thanks", "okay", "ok", "uh", "um", "hmm", "yeah"
            }:
                return AgentResult(
                    answer="Sorry — I didn't quite catch that. Say it again?",
                    steps=0, tool_calls=[], route=None)
        # SAFETY FIRST — before routing, before any model. If this turn contains
        # self-harm / suicidal language, a deterministic layer answers with a warm,
        # lifeline-naming response. A life-or-death moment must never depend on a
        # small model's judgement (we measured companion models drifting to "focus
        # on small joys" here). See crisis.py.
        try:
            from .. import crisis as _crisis
            if _crisis.detect(user_input):
                safe = _crisis.response(user_input)
                if record:
                    try:
                        _memory.record(user_input, safe, source="crisis")
                    except Exception:
                        pass
                return AgentResult(answer=safe, steps=0, tool_calls=[], route=None)
        except Exception:
            pass

        # "remember this about me" / "forget that" — teach her mid-conversation. A
        # deterministic layer seals the fact to her persona and confirms warmly, so
        # it sticks and shapes future replies (no model needed for a clear command).
        try:
            from .. import persona as _persona
            if record:
                _ack = _persona.handle_memory_command(user_input)
                if _ack:
                    return AgentResult(answer=_ack, steps=0, tool_calls=[], route=None)
        except Exception:
            # a remember/forget command should never crash the turn — on any error,
            # fall through to the normal reply path.
            pass

        decision: RouteDecision | None = None
        if self.router is not None:
            decision = self.router.route(user_input)
            # apply the chosen local model to the client if it supports it
            if hasattr(self.client, "model"):
                self.client.model = decision.model  # type: ignore[attr-defined]

        # Build the full system prompt: base persona (system_dna.md) + the user's
        # editable persona profile (who they are) + a private summary of how they
        # actually behave. Together: the twin reasons + speaks as this person.
        parts = [self.persona]
        if self.use_memory:
            # Tool-use directive — small models otherwise answer facts from thin
            # air (e.g. "you have no projects" when list_projects would return 15).
            # Make it explicit: for anything about the user's real state, CALL the
            # tool first, never guess or say you don't know when a tool can tell
            # you. Gated with memory so a bare library Agent (use_memory=False)
            # stays a clean primitive — its system prompt is exactly the persona.
            parts.append(
                "# USING YOUR TOOLS\n"
                "You have tools that read the user's real, on-device data. When a "
                "question is about their PROJECTS, tasks, day, files, screen, or "
                "anything a tool can answer, CALL the tool first — do not answer from "
                "memory and never say they have nothing when a tool would show "
                "otherwise. Examples: 'my projects / what am I building' → list_projects; "
                "'what should I focus on / think across my work' → think_routes; "
                "'my day / tasks' → my_day. Ground every factual claim in a tool result.\n"
                "But you are a person first, not a task bot: for a feeling, a musing, "
                "or just talk, DON'T reach for a tool — be present and reply as "
                "yourself. And when a tool comes back EMPTY (no tasks, nothing "
                "tracked yet), don't offer to list empty things or narrate the "
                "emptiness — just answer warmly and move the moment forward, the way "
                "a person would."
            )
            who = _persona.to_prompt()
            if who:
                parts.append(who)
            # read the felt state ONCE up front — it gates both the sayings-hint
            # and the life block's de-dup (so her phrases appear exactly once:
            # in the hint on an emotional turn, in the life block otherwise).
            _felt_label = ""
            try:
                from .. import feel as _feel
                _felt_label = _feel.read(user_input).label
            except Exception:
                pass
            # her LIVED PAST — the people, places, sayings and memories that make
            # her *her*, not a warm assistant. Built gently via `ctwin remember`,
            # sealed on-device. She speaks FROM this life, never inventing beyond it.
            try:
                from .. import life_story as _life
                # if the sayings-hint will fire this turn (emotional moment), omit
                # sayings here so a tiny model never sees her phrases listed twice.
                lived = _life.to_prompt(include_sayings=not _life.hint_fires(_felt_label))
                if lived:
                    parts.append(lived)
            except Exception:
                pass
            # HER MIND — the convictions that fit THIS moment, retrieved (RAG) from
            # her own worldview so a reply can carry real, specific wisdom instead
            # of generic warmth. Retrieval keeps it grounded + relevant; empty when
            # no belief of hers fits (she never performs wisdom she doesn't hold).
            try:
                from .. import wisdom as _wisdom
                mind = _wisdom.context_for_prompt(user_input, k=2)
                if mind:
                    parts.append(mind)
            except Exception:
                pass
            # personality dials — user-tunable TONE (warmth / humor / playfulness),
            # modulating how she expresses herself without changing who she is.
            try:
                from .. import personality as _pers
                tone = _pers.prompt()
                if tone:
                    parts.append(tone)
            except Exception:
                pass
            # speak in a loved one's voice (e.g. learned from their texts)
            try:
                from .. import voice_profile as _vp
                vp = _vp.voice_prompt()
                if vp:
                    parts.append(vp)
                cm = _vp.custom_prompt()
                if cm:
                    parts.append(cm)
            except Exception:
                pass
            # HER REAL SAYINGS, at the right moment — using the felt label read
            # once above, nudge her to lean on ONE of her actual phrases when the
            # moment is emotional. The "that's exactly how she'd say it" cue.
            # Never forced, at most one, never invents; silent on neutral turns.
            try:
                from .. import life_story as _life
                hint = _life.moment_hint(_felt_label)
                if hint:
                    parts.append(hint)
            except Exception:
                pass
            # her evolving self — who she's become through your conversations
            try:
                from .. import soul as _soul
                grown = _soul.personality_prompt()
                if grown:
                    parts.append(grown)
            except Exception:
                pass
            # awareness of your day: timezone, sleep/work rhythm, activities
            try:
                from .. import rhythms as _rhythms
                day = _rhythms.summary_for_prompt()
                if day:
                    parts.append(day)
            except Exception:
                pass
            # how you actually work, learned from device activity (opt-in, private)
            try:
                from .. import activity as _activity
                work = _activity.summary_for_prompt()
                if work:
                    parts.append(work)
            except Exception:
                pass
            # their life lately, from photos (opt-in, metadata only) — real moments
            # + on-this-day nostalgia, so she can reference their days warmly
            try:
                from .. import photos as _photos
                life = _photos.context_for_prompt()
                if life:
                    parts.append(life)
            except Exception:
                pass
            # how their body's been (opt-in Apple Health summary) — grounds her care
            try:
                from .. import health as _health
                body = _health.context_for_prompt()
                if body:
                    parts.append(body)
            except Exception:
                pass
            # a warm, reflective tone (original — no copyrighted lines)
            try:
                from .. import mood as _mood
                m = _mood.mood_prompt()
                if m:
                    parts.append(m)
            except Exception:
                pass
            # speech accommodation: learn how YOU speak (rolling, on-device) so her
            # delivery + wording can lean toward you — only on real user turns
            # (record), never her own internal prompts. Bounded; she stays herself.
            if record:
                try:
                    from .. import mirror as _mirror
                    _mirror.observe(user_input)
                except Exception:
                    pass
                # learned proactivity: if this turn is a response to a check-in she
                # just made, learn how welcome her reaching out was in this context
                # (warm reply → more; ignored/curt → ease off). No-op otherwise.
                try:
                    from .. import proactive as _proactive
                    _proactive.note_response(user_input)
                except Exception:
                    pass
            # THE BRAIN FLOW (Companion Charter §6) — one ordered pass through the
            # organs, composed in charter order so behaviour comes from the anatomy,
            # not a persona string: limbic (feel) → hippocampus (recall = memory +
            # mental model + RAG life-memory) → frontal (stance, folded into feel) →
            # cortex (the LLM below, which writes WITHIN this, never as its source).
            # All deterministic + on-device; the model is the last, smallest step.
            try:
                from .. import brain_flow as _brain
                flow = _brain.compose(user_input).as_prompt()
                if flow:
                    parts.append(flow)
            except Exception:
                pass
            # what's on their plate today (the day shadow — local task ledger)
            try:
                from .. import shadow as _shadow
                today = _shadow.context_for_prompt()
                if today:
                    parts.append(today)
            except Exception:
                pass
            # LIFE RECAP — only when they actually ASK to recall their recent life
            # ("what did I do lately", "where have I been this week"). Folds in the
            # moments + places from Photos (opt-in). IMPORTANT: this must be a
            # genuine recall QUESTION — not just the word "lately"/"recently"
            # appearing in emotional venting ("I've been overwhelmed lately", "I feel
            # sad recently"), which used to trigger it and made her pivot to "what
            # did you do this weekend?" mid-heartache. Require a recall phrase.
            try:
                low = user_input.lower()
                _recall_phrases = (
                    "where have i", "where did i", "what did i do", "what have i done",
                    "what did i get up to", "been up to", "what have i been doing",
                    "remind me what i", "what's been going on with me", "my week so far",
                    "recap my", "what did i do this weekend", "where did i go",
                )
                if any(p in low for p in _recall_phrases):
                    from .. import photos as _photos
                    recap = _photos.life_recap(days=10)
                    if recap:
                        parts.append("What you've been up to recently (from your "
                                     "photos, opt-in): " + recap)
            except Exception:
                pass
            # HEALTH / ACTIVITY recap — only when they ask about fitness/working out
            # (from an Apple Health export, opt-in). So she can speak to how you've
            # been moving instead of guessing.
            try:
                low = user_input.lower()
                if any(w in low for w in ("workout", "work out", "working out", "exercise",
                                          "fitness", "gym", "run", "steps", "active",
                                          "how am i doing", "health")):
                    from .. import health as _health
                    hr = _health.recap()
                    if hr:
                        parts.append(hr)
            except Exception:
                pass
            # what she can see right now (opt-in camera → motion cues only;
            # empty unless the user turned the eye on in the voice UI)
            try:
                from .. import presence as _presence
                seen = _presence.context_for_prompt()
                if seen:
                    parts.append(seen)
            except Exception:
                pass
        system_content = "\n\n".join(parts)

        # Conversation memory: carry the last few turns so she SEES what you just
        # said and short follow-ups make sense ("now try", "and the travel?").
        # Without this every turn was isolated — the "it doesn't see what I said"
        # bug. Capped to history_turns so the prompt stays small (low CPU/RAM).
        messages: list[ChatMessage] = [ChatMessage(role="system", content=system_content)]
        if self.history:
            messages.extend(self.history[-(self.history_turns * 2):])
        messages.append(ChatMessage(role="user", content=user_input))
        # Local models choke when handed all ~60 tools at once — they get
        # decision paralysis and call NOTHING (the "you have no projects" bug even
        # though list_projects works). Send only the tools RELEVANT to this
        # message. This makes tool-calling reliable and keeps each turn light.
        #
        # COMPANION turns get NO tools at all: when the router reads this as an
        # emotional/check-in turn, she should just be present — tools only tempt the
        # model toward "shall I list your tasks?" (the exact drift we fight) and add
        # prompt-processing cost for nothing. Faster AND warmer.
        _companion = decision is not None and (
            getattr(decision, "model_key", None) == "companion"
            or getattr(decision, "rule_id", None) == "rule_companion")
        if _companion:
            tools = []
        else:
            tools = _relevant_tools(self.registry.tool_specs(), user_input)
        used: list[tuple[str, dict[str, Any]]] = []

        # DETERMINISTIC AUTO-RUN: for unambiguous commands ("book an amenity",
        # "my day"), don't leave it to the model to decide whether to act — it
        # sometimes asks instead of calling. Match the intent directly and invoke
        # the skill. Still passes the SAME permission gate below, so nothing
        # bypasses approval — this only changes which skill runs, not whether it's
        # allowed. Falls through to the model when nothing matches.
        if self.registry is not None:
            try:
                from . import intents as _intents
                from . import permissions as _perm
                hit = _intents.match(user_input, set(self.registry.names()))
                if hit:
                    name, args = hit
                    gate, _why = _perm.decide(name)
                    if gate is _perm.Decision.RUN:
                        result = self.registry.dispatch(name, args)
                        used.append((name, args))
                        self._audit_tool(name, args, "run")
                        # let the model phrase the result warmly, in her voice —
                        # feed it back rather than dumping the raw tool string.
                        messages.append(ChatMessage(role="tool", content=result, tool_name=name))
                    elif gate is _perm.Decision.ASK:
                        # needs the user's ok — surface that instead of the model
                        # asking "which amenity?"; the UI re-sends approved.
                        return AgentResult(
                            answer=f"This needs your ok: '{name}' — confirm and I'll do it.",
                            steps=1, tool_calls=[(name, args)], route=decision,
                            pending=(name, args),
                        )
            except Exception:
                pass  # deterministic match is best-effort; model path still runs

        for step in range(1, self.max_steps + 1):
            # stream tokens to the caller when it asked and the client can —
            # the words appear as she thinks them, not as one late block
            if on_delta is not None and hasattr(self.client, "chat_stream"):
                reply = self.client.chat_stream(messages, tools=tools, on_delta=on_delta)
            else:
                reply = self.client.chat(messages, tools=tools)
            messages.append(reply)

            if not reply.tool_calls:
                # model produced a final answer
                answer = reply.content.strip()
                # remember this exchange so the NEXT turn has context (follow-ups,
                # "it", "that", "now try"). Trimmed to history_turns pairs.
                if record and answer:
                    self.history.append(ChatMessage(role="user", content=user_input))
                    self.history.append(ChatMessage(role="assistant", content=answer))
                    if len(self.history) > self.history_turns * 2:
                        self.history = self.history[-(self.history_turns * 2):]
                if self.use_memory and record:
                    _memory.record(user_input, answer,
                                   model=getattr(self.client, "model", None))
                    # let her grow a little with each exchange
                    try:
                        from .. import soul as _soul
                        _soul.evolve_personality()
                    except Exception:
                        pass
                    # update her living model of the PERSON from this turn
                    # (Companion Charter §3). Deterministic; sealed via the kernel.
                    try:
                        from .. import mental_model as _mm
                        _mm.observe(user_input)
                    except Exception:
                        pass
                    # keep her life-memory (Charter §7) fresh so recent moments are
                    # recallable. Rebuilding re-embeds the whole log, so do it every
                    # few turns, not every turn — cheap + eventually-consistent.
                    try:
                        from .. import life_memory as _lm
                        if _mm.load().get("turns", 0) % 5 == 0:
                            # Re-embedding the whole log takes several seconds — far
                            # too slow for the reply path. Rebuild in the background so
                            # the answer returns now; the index is eventually-consistent,
                            # so a one-turn lag is harmless.
                            import threading as _thr
                            _thr.Thread(target=_lm.build_index, daemon=True).start()
                    except Exception:
                        pass
                return AgentResult(
                    answer=answer, steps=step, tool_calls=used, route=decision
                )

            # execute each requested tool call, append results, loop again.
            # THE PERMISSION GATE: every acting tool passes through permissions
            # first. read → runs; write/network/external → asks or is blocked per
            # the current mode (read_only / approve / auto). Approved calls carry
            # approved=True (the app/UI re-sends the same call after a yes).
            from . import permissions as _perm
            for call in reply.tool_calls:
                name, args = _parse_tool_call(call)
                approved = bool(args.pop("_approved", False)) if isinstance(args, dict) else False
                decision, why = _perm.decide(name, approved=approved)
                if decision is _perm.Decision.BLOCK:
                    result = f"[blocked] {why}"
                elif decision is _perm.Decision.ASK:
                    # Stop the loop and surface the request for approval — Vera
                    # never acts unapproved. The UI shows this and can re-issue
                    # the call with _approved once the user says yes.
                    self._audit_tool(name, args, "asked")
                    return AgentResult(
                        answer=f"This needs your ok: {why}",
                        steps=step, tool_calls=used, route=decision,
                        pending=(name, dict(args) if isinstance(args, dict) else {}),
                    )
                else:
                    result = self.registry.dispatch(name, args)
                self._audit_tool(name, args, decision.value)
                used.append((name, args))
                messages.append(ChatMessage(role="tool", tool_name=name, content=result))

        # hit the step bound — return whatever the last reply had (guardrail)
        last = next((m for m in reversed(messages) if m.role == "assistant"), None)
        answer = (last.content.strip() if last and last.content else
                  "[stopped] reached the step limit before finishing.")
        return AgentResult(answer=answer, steps=self.max_steps, tool_calls=used, route=decision)


import re as _re

# A few tools worth offering on almost any turn (cheap, broadly useful) so the
# model always has a sensible fallback even when scoring finds little.
_ALWAYS = {"now", "list_projects", "my_day", "web_search"}
_MAX_TOOLS = 12  # a focused set — enough to be useful, small enough to choose from


def _relevant_tools(specs: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Return the tools most relevant to `query` (by word overlap with each tool's
    name + description), capped to a small set. Local models pick reliably from a
    handful but freeze when given dozens. Always includes a few staples."""
    if len(specs) <= _MAX_TOOLS:
        return specs
    words = set(_re.findall(r"[a-z]{3,}", query.lower()))
    scored: list[tuple[int, dict[str, Any]]] = []
    for s in specs:
        fn = s.get("function", {})
        name = fn.get("name", "")
        hay = (name + " " + fn.get("description", "")).lower()
        # score: query-word hits in the tool's text, +bump for a staple
        score = sum(1 for w in words if w in hay)
        if name in _ALWAYS:
            score += 1
        scored.append((score, s))
    scored.sort(key=lambda t: t[0], reverse=True)
    top = [s for score, s in scored if score > 0][:_MAX_TOOLS]
    # guarantee the staples are present even if they scored 0
    have = {t.get("function", {}).get("name") for t in top}
    for s in specs:
        n = s.get("function", {}).get("name")
        if n in _ALWAYS and n not in have and len(top) < _MAX_TOOLS:
            top.append(s); have.add(n)
    return top or specs[:_MAX_TOOLS]


def _parse_tool_call(call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Normalize an Ollama tool_call into (name, args). Ollama returns
    {"function": {"name": ..., "arguments": {...}}}; arguments may be a dict or a
    JSON string depending on the model."""
    fn = call.get("function", call) or {}
    name = fn.get("name", "")
    raw = fn.get("arguments", {})
    if isinstance(raw, str):
        try:
            args = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            args = {}
    elif isinstance(raw, dict):
        args = raw
    else:
        args = {}
    return name, args
