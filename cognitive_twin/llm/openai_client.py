"""
OpenAI-compatible client — drives any local server that speaks the OpenAI
``/v1/chat/completions`` API: LM Studio, llama.cpp ``--api``, Jan, vLLM, LocalAI,
and Unhosted. Stdlib only (urllib), same as the Ollama client — no SDK, no cloud.

It mirrors :class:`~cognitive_twin.llm.ollama_client.OllamaClient` so the agent
loop and router treat both backends identically. The interesting work is the
two-way translation between Ollama's tool-call shape (what the agent loop speaks)
and OpenAI's tool-call shape (what these servers expect):

  - outgoing: tool *arguments* must be a JSON **string**, and an assistant message
    that carries ``tool_calls`` must have ``content: null``; each ``tool`` reply
    must reference the assistant's ``tool_call_id``.
  - incoming: OpenAI ``tool_calls`` are reshaped into the Ollama-style dicts the
    loop already knows how to run.

Everything stays on the machine: the base URL points at a local server.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .ollama_client import ChatMessage


class OpenAIError(RuntimeError):
    """Raised when the OpenAI-compatible server is unreachable or errors."""


class OpenAIClient:
    def __init__(
        self,
        model: str = "local-model",
        host: str = "http://localhost:1234/v1",
        timeout: float = 120.0,
        temperature: float = 0.4,
        api_key: str = "",
    ) -> None:
        self.model = model
        self.host = self._normalize_host(host)
        self.timeout = timeout
        self.temperature = temperature
        # Only send Authorization when a real key is configured. Some local
        # servers (e.g. Unhosted's :7777/v1) reject a bogus bearer token with
        # 401, so a blank key must mean "no auth header" — not "Bearer not-needed".
        self.api_key = api_key

    @staticmethod
    def _normalize_host(host: str) -> str:
        """Ensure the base URL ends in ``/v1`` (and has no trailing slash), so
        callers can pass either ``http://localhost:1234`` or ``…/v1``."""
        h = host.rstrip("/")
        if not h.endswith("/v1"):
            h = h + "/v1"
        return h

    # ---- health -------------------------------------------------------------
    def is_up(self) -> bool:
        try:
            self._get("/models", timeout=4.0)
            return True
        except OpenAIError:
            return False

    def available_models(self) -> list[str]:
        try:
            data = self._get("/models", timeout=4.0)
        except OpenAIError:
            return []
        # OpenAI shape: {"data": [{"id": "..."}, ...]}
        return [m.get("id", "") for m in data.get("data", []) if m.get("id")]

    def ensure_ready(self) -> None:
        """Raise a friendly OpenAIError if the server is down."""
        if not self.is_up():
            raise OpenAIError(
                f"No OpenAI-compatible server reachable at {self.host}. Start your "
                f"local server (e.g. LM Studio ▸ Developer ▸ Start Server), then retry."
            )

    # ---- chat ---------------------------------------------------------------
    def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatMessage:
        """One non-streaming chat turn. Returns the assistant message (which may
        carry tool_calls reshaped into the Ollama format the agent loop runs)."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._to_openai_messages(messages),
            "stream": False,
            "temperature": self.temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        data = self._post("/chat/completions", payload)
        choices = data.get("choices") or [{}]
        msg = (choices[0] or {}).get("message", {}) or {}
        return ChatMessage(
            role=msg.get("role", "assistant"),
            content=msg.get("content") or "",
            tool_calls=self._from_openai_tool_calls(msg.get("tool_calls") or []),
        )

    # ---- translation: Ollama shape → OpenAI shape ---------------------------
    def _to_openai_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        # Track the id we minted for each assistant tool_call by name, so the
        # following tool reply can reference the matching tool_call_id.
        last_call_id_by_name: dict[str, str] = {}
        for m in messages:
            if m.role == "assistant" and m.tool_calls:
                calls = []
                for i, tc in enumerate(m.tool_calls):
                    fn = tc.get("function", {}) or {}
                    name = fn.get("name", "")
                    args = fn.get("arguments", {})
                    # OpenAI wants arguments as a JSON string.
                    if not isinstance(args, str):
                        args = json.dumps(args)
                    call_id = tc.get("id") or f"call_{i}"
                    last_call_id_by_name[name] = call_id
                    calls.append({
                        "id": call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": args},
                    })
                # content must be null when tool_calls are present
                out.append({"role": "assistant", "content": None, "tool_calls": calls})
            elif m.role == "tool":
                out.append({
                    "role": "tool",
                    "tool_call_id": last_call_id_by_name.get(m.tool_name or "", "call_0"),
                    "content": m.content,
                })
            else:
                out.append({"role": m.role, "content": m.content})
        return out

    # ---- translation: OpenAI reply → Ollama shape ---------------------------
    def _from_openai_tool_calls(self, tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Reshape OpenAI tool_calls into the Ollama-style dicts the agent loop
        executes. Arguments come back as a JSON string; parse to a dict."""
        out: list[dict[str, Any]] = []
        for tc in tool_calls:
            fn = tc.get("function", {}) or {}
            args = fn.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args or "{}")
                except json.JSONDecodeError:
                    args = {}
            out.append({
                "id": tc.get("id", ""),
                "function": {"name": fn.get("name", ""), "arguments": args},
            })
        return out

    # ---- transport ----------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:  # omit auth entirely for keyless local servers
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.host + path, data=body, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise OpenAIError(f"OpenAI-compatible request to {path} failed: {e}") from e
        except json.JSONDecodeError as e:
            raise OpenAIError(f"Server returned invalid JSON from {path}: {e}") from e

    def _get(self, path: str, timeout: float | None = None) -> dict[str, Any]:
        req = urllib.request.Request(self.host + path, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise OpenAIError(f"OpenAI-compatible request to {path} failed: {e}") from e
        except json.JSONDecodeError as e:
            raise OpenAIError(f"Server returned invalid JSON from {path}: {e}") from e
