"""
Multi-backend (Ollama + OpenAI-compatible / LM Studio) tests.

Proves model id tagging, backend selection, and the OpenAI tool-call translation
without needing a live LM Studio / Ollama server (transport is monkeypatched).

Run: python -m pytest tests/ -q   (or: python tests/test_providers.py)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cognitive_twin.llm.ollama_client import ChatMessage, OllamaClient  # noqa: E402
from cognitive_twin.llm.openai_client import OpenAIClient  # noqa: E402
from cognitive_twin.llm import providers  # noqa: E402


# ---- model id tagging -------------------------------------------------------

def test_split_model_id():
    assert providers.split_model_id("llama3.2") == (None, "llama3.2")
    # an Ollama ':' tag is NOT a provider prefix
    assert providers.split_model_id("qwen2.5:3b") == (None, "qwen2.5:3b")
    assert providers.split_model_id("lmstudio/qwen2.5-7b") == ("lmstudio", "qwen2.5-7b")
    print("✓ model id split: bare names vs provider-tagged ids")


def test_backend_off_by_default(monkeyenv):
    # No env, no config, and Unhosted auto-detect disabled → OpenAI backend off
    # (Ollama only). CTWIN_NO_UNHOSTED keeps this deterministic even if an
    # Unhosted daemon happens to be running on this machine.
    monkeyenv("CTWIN_NO_UNHOSTED", "1")
    assert providers.openai_base_url({}) is None
    mb = providers.MultiBackend()
    assert mb.openai_base is None
    monkeyenv("CTWIN_NO_UNHOSTED", None)
    print("✓ OpenAI backend is off unless explicitly configured")


def test_backend_enabled_by_env(monkeyenv):
    # Disable Unhosted auto-detect so we test the LM Studio / explicit-base paths
    # deterministically (Unhosted, if running, would otherwise take priority).
    monkeyenv("CTWIN_NO_UNHOSTED", "1")
    monkeyenv("CTWIN_USE_LMSTUDIO", "1")
    assert providers.openai_base_url({}) == providers.DEFAULT_OPENAI_BASE
    monkeyenv("CTWIN_USE_LMSTUDIO", None)
    monkeyenv("CTWIN_OPENAI_BASE", "http://localhost:8080/v1")
    assert providers.openai_base_url({}) == "http://localhost:8080/v1"
    monkeyenv("CTWIN_OPENAI_BASE", None)
    monkeyenv("CTWIN_NO_UNHOSTED", None)
    print("✓ OpenAI backend enabled via CTWIN_USE_LMSTUDIO / CTWIN_OPENAI_BASE")


def test_client_for_selects_backend():
    mb = providers.MultiBackend(openai_base="http://localhost:1234/v1", openai_label="lmstudio")
    assert isinstance(mb.client_for("llama3.2"), OllamaClient)
    oai = mb.client_for("lmstudio/qwen2.5-7b")
    assert isinstance(oai, OpenAIClient)
    assert oai.model == "qwen2.5-7b"  # prefix stripped for the wire call
    # unknown prefix → falls back to Ollama (and keeps the bare name)
    assert isinstance(mb.client_for("mystery/x"), OllamaClient)
    print("✓ client_for routes a model id to the right backend")


# ---- merged discovery (transport mocked) ------------------------------------

def test_list_models_merges_and_tags(monkeypatch_method):
    monkeypatch_method(OllamaClient, "available_models", lambda self: ["llama3.2", "qwen2.5:3b"])
    monkeypatch_method(OpenAIClient, "available_models", lambda self: ["qwen2.5-7b-instruct"])
    mb = providers.MultiBackend(openai_base="http://localhost:1234/v1", openai_label="lmstudio")
    models = mb.list_models()
    assert "llama3.2" in models and "qwen2.5:3b" in models
    assert "lmstudio/qwen2.5-7b-instruct" in models  # OpenAI models are tagged
    print("✓ list_models merges Ollama + OpenAI and tags the OpenAI ones")


# ---- OpenAI tool-call translation (the hard part) ---------------------------

def test_openai_message_translation():
    c = OpenAIClient(model="m", host="http://localhost:1234")  # no /v1 → normalized
    assert c.host == "http://localhost:1234/v1"

    msgs = [
        ChatMessage(role="system", content="sys"),
        ChatMessage(role="user", content="2+3?"),
        ChatMessage(role="assistant", content="",
                    tool_calls=[{"function": {"name": "add", "arguments": {"a": 2, "b": 3}}}]),
        ChatMessage(role="tool", tool_name="add", content="5"),
    ]
    oai = c._to_openai_messages(msgs)
    asst, tool = oai[2], oai[3]
    # OpenAI requires arguments as a JSON string and null content alongside tool_calls
    assert asst["content"] is None
    assert asst["tool_calls"][0]["function"]["arguments"] == json.dumps({"a": 2, "b": 3})
    # the tool reply must reference the assistant's tool_call id
    assert tool["tool_call_id"] == asst["tool_calls"][0]["id"]
    print("✓ OpenAI translation: tool_call_id wiring + JSON-string arguments")


def test_openai_parse_reply():
    c = OpenAIClient(model="m")
    got = c._from_openai_tool_calls([
        {"id": "call_0", "function": {"name": "add", "arguments": '{"a": 2}'}},
    ])
    assert got[0]["function"]["name"] == "add"
    assert got[0]["id"] == "call_0"
    print("✓ OpenAI reply → Ollama-shaped tool_calls the agent loop understands")


def test_openai_chat_roundtrip(monkeypatch_method):
    """A full chat() turn with the HTTP transport mocked."""
    captured = {}

    def fake_post(self, path, payload):
        captured["path"] = path
        captured["payload"] = payload
        return {"choices": [{"message": {"role": "assistant", "content": "The answer is 5."}}]}

    monkeypatch_method(OpenAIClient, "_post", fake_post)
    c = OpenAIClient(model="qwen2.5-7b", host="http://localhost:1234/v1")
    reply = c.chat([ChatMessage(role="user", content="2+3?")], tools=[{"type": "function"}])
    assert reply.content == "The answer is 5."
    assert captured["path"] == "/chat/completions"
    assert captured["payload"]["model"] == "qwen2.5-7b"
    assert captured["payload"]["tool_choice"] == "auto"
    print("✓ OpenAI chat(): builds the right payload and parses the reply")


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
        (test_split_model_id, {}),
        (test_backend_off_by_default, {"monkeyenv": monkeyenv}),
        (test_backend_enabled_by_env, {"monkeyenv": monkeyenv}),
        (test_client_for_selects_backend, {}),
        (test_list_models_merges_and_tags, {"monkeypatch_method": monkeypatch_method}),
        (test_openai_message_translation, {}),
        (test_openai_parse_reply, {}),
        (test_openai_chat_roundtrip, {"monkeypatch_method": monkeypatch_method}),
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
    print("\nall provider/backend tests passed.")


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
