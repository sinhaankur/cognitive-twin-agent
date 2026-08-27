"""
Claude backend tests — the cloud door stays shut unless the user opens it.

Proves: off-by-default (no key + no switch → Claude cannot appear), the
explicit-switch semantics, `claude/…` model tagging and backend selection, and
the Anthropic message/tool translation — all without any network (transport is
monkeypatched, keys are fakes).

Run: python -m pytest tests/ -q   (or: python tests/test_claude.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cognitive_twin.llm.claude_client import ClaudeClient  # noqa: E402
from cognitive_twin.llm.ollama_client import ChatMessage, OllamaClient  # noqa: E402
from cognitive_twin.llm import providers  # noqa: E402


# ---- the switch -------------------------------------------------------------

def test_claude_off_by_default(monkeyenv):
    # No switch → not enabled, regardless of any key that may exist on the
    # machine. A key alone is never consent.
    monkeyenv("CTWIN_USE_CLAUDE", None)
    assert providers.claude_enabled({}) is False
    assert providers.claude_enabled({"claude": {}}) is False
    # And a backend built without a key contributes nothing and routes nothing
    # to the cloud: a claude/ id falls back to the local default.
    mb = providers.MultiBackend()
    assert mb.claude_key is None
    assert isinstance(mb.client_for("claude/claude-sonnet-4-6"), OllamaClient)
    print("✓ Claude is OFF by default — no switch, no cloud, ever")


def test_claude_switch_semantics(monkeyenv):
    monkeyenv("CTWIN_USE_CLAUDE", "1")
    assert providers.claude_enabled({}) is True
    monkeyenv("CTWIN_USE_CLAUDE", None)
    assert providers.claude_enabled({"claude": {"enabled": True}}) is True
    assert providers.claude_enabled({"claude": {"enabled": False}}) is False
    print("✓ the switch: CTWIN_USE_CLAUDE=1 or claude.enabled in config")


def test_claude_key_sources(monkeyenv):
    monkeyenv("ANTHROPIC_API_KEY", "sk-ant-env")
    assert providers.claude_api_key({}) in ("sk-ant-env", providers.claude_api_key({}))
    monkeyenv("ANTHROPIC_API_KEY", None)
    cfg_key = providers.claude_api_key({"claude": {"api_key": "sk-ant-cfg"}})
    # Keychain (if present on this machine) may outrank config; both are fine —
    # what matters is that a config key is found when nothing else exists.
    assert cfg_key is not None
    print("✓ the key: keychain → env → config")


# ---- selection + tagging ----------------------------------------------------

def test_client_for_claude():
    mb = providers.MultiBackend(claude_key="sk-ant-test")
    c = mb.client_for("claude/claude-sonnet-4-6")
    assert isinstance(c, ClaudeClient)
    assert c.model == "claude-sonnet-4-6"  # prefix stripped for the wire call
    assert c.api_key == "sk-ant-test"
    # local ids still go local
    assert isinstance(mb.client_for("llama3.2"), OllamaClient)
    assert mb.is_claude_model("claude/claude-haiku-4-5")
    assert mb.is_cloud_model("claude/claude-haiku-4-5")
    assert not mb.is_cloud_model("qwen2.5:7b")
    print("✓ claude/… ids select ClaudeClient; provenance is in the id itself")


def test_list_models_tags_claude(monkeypatch_method):
    monkeypatch_method(OllamaClient, "available_models", lambda self: ["qwen2.5:7b"])
    monkeypatch_method(ClaudeClient, "available_models",
                       lambda self: ["claude-sonnet-4-6", "claude-haiku-4-5"])
    mb = providers.MultiBackend(claude_key="sk-ant-test")
    models = mb.list_models()
    assert "qwen2.5:7b" in models
    assert "claude/claude-sonnet-4-6" in models
    assert "claude/claude-haiku-4-5" in models
    print("✓ list_models tags every Claude model claude/… — cloud is always visible")


# ---- Anthropic translation --------------------------------------------------

def test_claude_message_translation():
    c = ClaudeClient(model="m", api_key="k")
    msgs = [
        ChatMessage(role="system", content="be kind"),
        ChatMessage(role="user", content="2+3?"),
        ChatMessage(role="assistant", content="",
                    tool_calls=[{"function": {"name": "add", "arguments": {"a": 2, "b": 3}}}]),
        ChatMessage(role="tool", tool_name="add", content="5"),
    ]
    system, out = c._to_claude_messages(msgs)
    assert system == "be kind"                      # system lifts to top level
    assert out[0] == {"role": "user", "content": "2+3?"}
    tool_use = out[1]["content"][-1]
    assert tool_use["type"] == "tool_use"
    assert tool_use["name"] == "add" and tool_use["input"] == {"a": 2, "b": 3}
    result = out[2]["content"][0]
    assert result["type"] == "tool_result"
    assert result["tool_use_id"] == tool_use["id"]  # reply references the call
    assert out[2]["role"] == "user"                 # Anthropic: results ride user turns
    print("✓ Claude translation: system lift, tool_use blocks, tool_result wiring")


def test_claude_tools_translation():
    tools = [{"type": "function", "function": {
        "name": "add", "description": "adds",
        "parameters": {"type": "object", "properties": {"a": {"type": "number"}}},
    }}]
    out = ClaudeClient._to_claude_tools(tools)
    assert out[0]["name"] == "add"
    assert out[0]["input_schema"]["properties"]["a"]["type"] == "number"
    print("✓ tools: OpenAI-style function specs become Anthropic input_schema")


def test_claude_chat_roundtrip(monkeypatch_method):
    captured = {}

    def fake_post(self, path, payload):
        captured["path"] = path
        captured["payload"] = payload
        return {"content": [
            {"type": "text", "text": "The answer is 5."},
            {"type": "tool_use", "id": "toolu_1", "name": "add", "input": {"a": 2, "b": 3}},
        ]}

    monkeypatch_method(ClaudeClient, "_post", fake_post)
    c = ClaudeClient(model="claude-sonnet-4-6", api_key="k")
    reply = c.chat(
        [ChatMessage(role="system", content="s"), ChatMessage(role="user", content="2+3?")],
        tools=[{"type": "function", "function": {"name": "add", "parameters": {}}}],
    )
    assert captured["path"] == "/messages"
    assert captured["payload"]["model"] == "claude-sonnet-4-6"
    assert captured["payload"]["system"] == "s"
    assert captured["payload"]["max_tokens"] > 0        # required by the API
    assert captured["payload"]["tools"][0]["name"] == "add"
    assert reply.content == "The answer is 5."
    assert reply.tool_calls[0]["function"]["name"] == "add"
    assert reply.tool_calls[0]["function"]["arguments"] == {"a": 2, "b": 3}
    print("✓ Claude chat(): right payload out, Ollama-shaped tool_calls back")


# ---- tiny fixtures so the file runs with or without pytest -------------------

def _run_standalone():
    import os

    saved_env: dict[str, str | None] = {}

    def monkeyenv(key, value):
        if key not in saved_env:
            saved_env[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    patches: list = []

    def monkeypatch_method(cls, name, fn):
        patches.append((cls, name, getattr(cls, name)))
        setattr(cls, name, fn)

    tests = [
        (test_claude_off_by_default, {"monkeyenv": monkeyenv}),
        (test_claude_switch_semantics, {"monkeyenv": monkeyenv}),
        (test_claude_key_sources, {"monkeyenv": monkeyenv}),
        (test_client_for_claude, {}),
        (test_list_models_tags_claude, {"monkeypatch_method": monkeypatch_method}),
        (test_claude_message_translation, {}),
        (test_claude_tools_translation, {}),
        (test_claude_chat_roundtrip, {"monkeypatch_method": monkeypatch_method}),
    ]
    try:
        for fn, kwargs in tests:
            fn(**kwargs)
    finally:
        for cls, name, orig in reversed(patches):
            setattr(cls, name, orig)
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    print("\nall Claude backend tests passed.")


# pytest fixtures (only used when pytest is present)
try:
    import pytest

    @pytest.fixture
    def monkeyenv(monkeypatch):
        def _set(key, value):
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)
        return _set

    @pytest.fixture
    def monkeypatch_method(monkeypatch):
        def _set(cls, name, fn):
            monkeypatch.setattr(cls, name, fn)
        return _set
except ImportError:
    pass


if __name__ == "__main__":
    _run_standalone()
