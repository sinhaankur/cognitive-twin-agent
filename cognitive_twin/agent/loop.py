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
    """Persona = the repo's system_dna.md if present, else a sane default."""
    for candidate in (
        Path(__file__).resolve().parents[2] / "system_dna.md",
        Path.cwd() / "system_dna.md",
    ):
        try:
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8")
        except OSError:
            pass
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
    ) -> None:
        self.client = client
        self.registry = registry or default_registry
        self.max_steps = max_steps
        self.persona = persona if persona is not None else _load_persona()
        # Optional policy-driven model router. When set, each run picks a local
        # model per the routing policy and applies it to the client. Left None in
        # tests so the scripted/mock client is used as-is.
        self.router = router

    def run(self, user_input: str) -> AgentResult:
        decision: RouteDecision | None = None
        if self.router is not None:
            decision = self.router.route(user_input)
            # apply the chosen local model to the client if it supports it
            if hasattr(self.client, "model"):
                self.client.model = decision.model  # type: ignore[attr-defined]

        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=self.persona),
            ChatMessage(role="user", content=user_input),
        ]
        tools = self.registry.tool_specs()
        used: list[tuple[str, dict[str, Any]]] = []

        for step in range(1, self.max_steps + 1):
            reply = self.client.chat(messages, tools=tools)
            messages.append(reply)

            if not reply.tool_calls:
                # model produced a final answer
                return AgentResult(
                    answer=reply.content.strip(), steps=step, tool_calls=used, route=decision
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
