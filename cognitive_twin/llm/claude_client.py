"""
Claude client — the ONE cloud door, and it only opens when the user opens it.

Vera is local-first: Ollama and OpenAI-compatible servers run on this machine.
But if the user already has Claude (an Anthropic API key), she can borrow its
mind for a turn — deliberately, never silently. The rules, in one place:

  - OFF by default. No key, no switch → this module is never even constructed,
    and nothing can leave the machine.
  - The switch is explicit (``CTWIN_USE_CLAUDE=1`` or ``claude.enabled`` in the
    agent config) AND a key must exist (Keychain via secrets_store, or env).
    Having a key alone is not consent; the switch alone has nothing to send.
  - Provenance is visible: Claude models are always tagged ``claude/…`` in the
    picker and in every route readout — the user can always see which turns
    used the cloud.
  - The router never auto-picks Claude. Policy routing chooses among local
    models only (guardrails.allowCloudFallback stays false); using Claude is
    the user's own pick, per conversation.

Stdlib only (urllib) like every other client — no SDK. Speaks the Anthropic
Messages API and translates to/from the Ollama shapes the agent loop runs.
Docs: https://docs.anthropic.com/en/api/messages
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .ollama_client import ChatMessage

API_BASE = "https://api.anthropic.com/v1"
API_VERSION = "2023-06-01"

# When the models endpoint can't be listed (rare), offer the stable aliases —
# current at time of writing; the live listing is always preferred.
FALLBACK_MODELS = ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5"]


class ClaudeError(RuntimeError):
    """Raised when Claude is unreachable, unauthorized, or errors."""


class ClaudeClient:
    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: str = "",
        timeout: float = 120.0,
        temperature: float = 0.4,
        max_tokens: int = 4096,
        base: str = API_BASE,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base = base.rstrip("/")

    # ---- health -------------------------------------------------------------
    def is_up(self) -> bool:
        try:
            self._get("/models?limit=1", timeout=4.0)
            return True
        except ClaudeError:
            return False

    def available_models(self) -> list[str]:
        """The live model list for this key; a short stable-alias fallback if the
        listing endpoint fails while the key clearly exists."""
        try:
            data = self._get("/models?limit=100", timeout=6.0)
        except ClaudeError:
            return list(FALLBACK_MODELS) if self.api_key else []
        return [m.get("id", "") for m in data.get("data", []) if m.get("id")]

    def ensure_ready(self) -> None:
        if not self.api_key:
            raise ClaudeError(
                "No Anthropic API key. Add one to the Keychain "
                "(secrets_store: ANTHROPIC_API_KEY) or the environment, "
                "and set CTWIN_USE_CLAUDE=1."
            )

    # ---- chat ---------------------------------------------------------------
    def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatMessage:
        """One non-streaming turn. Accepts/returns the same shapes as the local
        clients so the agent loop cannot tell the backends apart."""
        system, msgs = self._to_claude_messages(messages)
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": msgs,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = self._to_claude_tools(tools)
        data = self._post("/messages", payload)
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in data.get("content") or []:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": block.get("input") or {},
                    },
                })
        return ChatMessage(
            role="assistant",
            content="".join(text_parts),
            tool_calls=tool_calls,
        )

    # ---- translation: Ollama shape → Anthropic shape ------------------------
    def _to_claude_messages(
        self, messages: list[ChatMessage]
    ) -> tuple[str, list[dict[str, Any]]]:
        """System messages lift to the top-level ``system`` string; assistant
        tool_calls become ``tool_use`` blocks; tool replies become ``tool_result``
        blocks inside a user message (Anthropic's shape for tool output)."""
        system_parts: list[str] = []
        out: list[dict[str, Any]] = []
        last_call_id_by_name: dict[str, str] = {}
        for m in messages:
            if m.role == "system":
                if m.content:
                    system_parts.append(m.content)
            elif m.role == "assistant" and m.tool_calls:
                blocks: list[dict[str, Any]] = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                for i, tc in enumerate(m.tool_calls):
                    fn = tc.get("function", {}) or {}
                    name = fn.get("name", "")
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args or "{}")
                        except json.JSONDecodeError:
                            args = {}
                    call_id = tc.get("id") or f"toolu_{i}"
                    last_call_id_by_name[name] = call_id
                    blocks.append({
                        "type": "tool_use", "id": call_id,
                        "name": name, "input": args,
                    })
                out.append({"role": "assistant", "content": blocks})
            elif m.role == "tool":
                out.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": last_call_id_by_name.get(
                            m.tool_name or "", "toolu_0"),
                        "content": m.content,
                    }],
                })
            else:
                out.append({"role": m.role, "content": m.content})
        return "\n\n".join(system_parts), out

    @staticmethod
    def _to_claude_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """OpenAI-style function tools (what the registry defines) → Anthropic
        tools: parameters become input_schema, the wrapper drops away."""
        out: list[dict[str, Any]] = []
        for t in tools:
            fn = t.get("function", t) or {}
            out.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters")
                or {"type": "object", "properties": {}},
            })
        return out

    # ---- transport ----------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
        }

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=body, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
            except Exception:  # noqa: BLE001 - the status alone still tells the story
                pass
            if e.code == 401:
                raise ClaudeError(
                    "Claude rejected the API key (401). Check the key in the "
                    "Keychain / ANTHROPIC_API_KEY."
                ) from e
            raise ClaudeError(f"Claude request failed ({e.code}): {detail or e.reason}") from e
        except urllib.error.URLError as e:
            raise ClaudeError(f"Claude is unreachable: {e.reason}") from e
        except json.JSONDecodeError as e:
            raise ClaudeError(f"Claude returned invalid JSON: {e}") from e

    def _get(self, path: str, timeout: float | None = None) -> dict[str, Any]:
        req = urllib.request.Request(self.base + path, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            raise ClaudeError(f"Claude request to {path} failed: {e}") from e
        except json.JSONDecodeError as e:
            raise ClaudeError(f"Claude returned invalid JSON: {e}") from e
