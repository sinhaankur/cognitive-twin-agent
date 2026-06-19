"""
Persona + memory + skill-gate tests — protect the personalization core and the
opt-in safety of web/control skills. All offline; isolated temp dirs so nothing
touches the real ~/.cognitive-twin. No Ollama needed.

Run: python -m pytest tests/ -q   (or: python tests/test_persona_memory.py)
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Point persona + memory at a throwaway dir BEFORE importing the modules that read them.
_TMP = tempfile.mkdtemp()
os.environ["CTWIN_MEMORY_DIR"] = _TMP
os.environ["CTWIN_PERSONA_DIR"] = _TMP
os.environ.pop("CTWIN_WEB", None)        # ensure web is OFF for gate tests
os.environ.pop("CTWIN_CONTROL", None)    # ensure control is OFF

from cognitive_twin import persona as P          # noqa: E402
from cognitive_twin import memory as M           # noqa: E402
from cognitive_twin.agent.loop import Agent       # noqa: E402
from cognitive_twin.llm.ollama_client import ChatMessage  # noqa: E402
from cognitive_twin.skills.base import SkillRegistry  # noqa: E402
from cognitive_twin.skills import builtin          # noqa: E402,F401
from cognitive_twin.skills.base import default_registry  # noqa: E402


def test_persona_compiles_into_prompt():
    P.clear()
    p = P.Persona(name="Ankur", likes=["Rust"], dislikes=["hype"],
                  values=["privacy"], style="concise")
    P.save(p)
    block = P.to_prompt()
    assert "Ankur" in block and "Rust" in block and "privacy" in block
    assert "hype" in block
    print("✓ persona: compiles likes/dislikes/values into the prompt")


def test_persona_roundtrip_and_clear():
    P.clear()
    P.save(P.Persona(name="Test", traits=["calm"]))
    assert P.load().name == "Test"
    assert P.clear() is True
    assert P.load().is_empty()
    print("✓ persona: save → load → clear roundtrip")


def test_memory_records_and_summarizes():
    M.clear()
    M.record("how do I use rust traits", "...", model="m")
    M.record("rust borrow checker help", "...", model="m")
    pats = M.patterns()
    assert pats["count"] == 2
    assert "rust" in pats["topics"]
    assert "rust" in M.summary_for_prompt().lower()
    M.clear()
    print("✓ memory: records + derives recurring topics")


class _CaptureClient:
    """Mock model client that records the system prompt it was given."""
    def __init__(self):
        self.model = "mock"
        self.system_seen = ""
    def chat(self, messages, tools=None):
        for m in messages:
            if m.role == "system":
                self.system_seen = m.content
        return ChatMessage(role="assistant", content="ok")


def test_agent_injects_persona_and_memory():
    P.clear(); M.clear()
    P.save(P.Persona(name="Ankur", likes=["local-first"]))
    M.record("tell me about ollama", "...", model="m")
    client = _CaptureClient()
    agent = Agent(client=client, registry=SkillRegistry(), persona="BASE", use_memory=True)
    agent.run("hi")
    # base persona + the WHO YOU ARE block + the memory summary all present
    assert "BASE" in client.system_seen
    assert "Ankur" in client.system_seen and "local-first" in client.system_seen
    assert "ollama" in client.system_seen.lower()
    P.clear(); M.clear()
    print("✓ agent: injects base persona + profile + memory into the system prompt")


def test_agent_without_memory_stays_clean():
    P.clear(); M.clear()
    P.save(P.Persona(name="ShouldNotLeak"))
    client = _CaptureClient()
    # use_memory defaults False → no persona/memory injected (library/test safety)
    agent = Agent(client=client, registry=SkillRegistry(), persona="BASE")
    agent.run("hi")
    assert client.system_seen == "BASE"
    assert "ShouldNotLeak" not in client.system_seen
    P.clear()
    print("✓ agent: use_memory off → only base persona (no surprise injection)")


def test_web_skills_off_by_default():
    assert "[web disabled]" in default_registry.dispatch("web_search", {"query": "x"})
    assert "[web disabled]" in default_registry.dispatch("fetch_url", {"url": "https://example.com"})
    print("✓ skills: web search/fetch refuse when CTWIN_WEB is unset")


def test_control_skills_off_by_default():
    out = default_registry.dispatch("open_app", {"name": "Calculator"})
    assert "[control disabled]" in out
    print("✓ skills: screen control refuses when CTWIN_CONTROL is unset")


def test_greeting_is_time_aware():
    out = default_registry.dispatch("greeting", {})
    assert any(p in out for p in ("Good morning", "Good afternoon", "Good evening"))
    print("✓ skills: greeting is time-aware")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nall persona/memory/skill tests passed.")
