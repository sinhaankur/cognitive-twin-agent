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
    # which model the router picked for this run (None when routing is off)
    route: RouteDecision | None = None


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

    def run(self, user_input: str, *, record: bool = True,
            on_delta: Any = None) -> AgentResult:
        """``record=False`` answers without writing to memory — for scripted,
        internal prompts (greetings, background reflections). The twin should
        learn from the USER, never from its own boilerplate."""
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
                "'my day / tasks' → my_day. Ground every factual claim in a tool result."
            )
            who = _persona.to_prompt()
            if who:
                parts.append(who)
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
            # the limbic + frontal read of THIS message: Vera's own felt state and
            # the stance she takes, decided by her own deterministic logic (not the
            # model). The model writes within it — this is what makes her feel like
            # a mind, not a context-follower. Works with or without a model.
            # (feel.directive reads the mirror lean too — voice + wording adapt.)
            try:
                from .. import feel as _feel
                d = _feel.directive(user_input)
                if d:
                    parts.append(d)
            except Exception:
                pass
            # Recall memories relevant to *this* message (falls back to the
            # standing habit summary when nothing specific matches). This is what
            # makes the twin feel like it remembers you, not just your stats.
            try:
                ctx = _memory.context_for(user_input)
            except Exception:
                ctx = _memory.summary_for_prompt()
            if ctx:
                parts.append(ctx)
            # what's on their plate today (the day shadow — local task ledger)
            try:
                from .. import shadow as _shadow
                today = _shadow.context_for_prompt()
                if today:
                    parts.append(today)
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

        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=system_content),
            ChatMessage(role="user", content=user_input),
        ]
        # Local models choke when handed all ~60 tools at once — they get
        # decision paralysis and call NOTHING (the "you have no projects" bug even
        # though list_projects works). Send only the tools RELEVANT to this
        # message. This makes tool-calling reliable and keeps each turn light.
        tools = _relevant_tools(self.registry.tool_specs(), user_input)
        used: list[tuple[str, dict[str, Any]]] = []

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
                if self.use_memory and record:
                    _memory.record(user_input, answer,
                                   model=getattr(self.client, "model", None))
                    # let her grow a little with each exchange
                    try:
                        from .. import soul as _soul
                        _soul.evolve_personality()
                    except Exception:
                        pass
                return AgentResult(
                    answer=answer, steps=step, tool_calls=used, route=decision
                )

            # execute each requested tool call, append results, loop again
            for call in reply.tool_calls:
                name, args = _parse_tool_call(call)
                result = self.registry.dispatch(name, args)
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
