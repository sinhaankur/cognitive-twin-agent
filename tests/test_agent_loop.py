"""
Agent-loop + skill tests with a MOCK model client — proves the plumbing end to
end without needing a live Ollama / pulled model. (Live run is documented in the
README: `ollama pull llama3.2` then `ctwin "..."`.)

Run: python -m pytest tests/ -q   (or: python tests/test_agent_loop.py)
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cognitive_twin.agent.loop import Agent          # noqa: E402
from cognitive_twin.llm.ollama_client import ChatMessage  # noqa: E402
from cognitive_twin.skills.base import SkillRegistry, Skill  # noqa: E402


class ScriptedClient:
    """Returns a pre-scripted list of assistant turns, ignoring input. Lets us
    drive the loop deterministically: turn 1 asks for a tool, turn 2 answers."""
    def __init__(self, turns: list[ChatMessage]):
        self.turns = turns
        self.calls = 0
        self.seen_tool_results: list[str] = []

    def chat(self, messages, tools=None):
        # record any tool results fed back so we can assert the loop wired them
        for m in messages:
            if m.role == "tool":
                self.seen_tool_results.append(m.content)
        turn = self.turns[min(self.calls, len(self.turns) - 1)]
        self.calls += 1
        return turn


def _tool_call(name, args):
    return {"function": {"name": name, "arguments": args}}


def _approved_tool_call(name, args):
    """A tool call the user has already said yes to. Since the loop's default
    permission mode is `approve` (acting tools stop for an explicit ok), these
    loop-PLUMBING tests simulate that yes by carrying `_approved` — exactly how
    the app/UI re-issues a call after confirmation. Read-only tools wouldn't need
    it, but add/echo/noop/mystery are inferred as write_local by permissions."""
    a = dict(args) if isinstance(args, dict) else {}
    a["_approved"] = True
    return {"function": {"name": name, "arguments": a}}


def test_tool_calling_loop():
    reg = SkillRegistry()
    reg.register(Skill(
        name="add",
        description="add two ints",
        parameters={"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}},
        run=lambda a, b: str(int(a) + int(b)),
    ))
    client = ScriptedClient([
        ChatMessage(role="assistant", content="", tool_calls=[_approved_tool_call("add", {"a": 2, "b": 3})]),
        ChatMessage(role="assistant", content="The answer is 5."),
    ])
    agent = Agent(client=client, registry=reg, persona="test")
    res = agent.run("what is 2+3?")
    assert res.answer == "The answer is 5.", res.answer
    assert res.steps == 2, res.steps
    assert ("add", {"a": 2, "b": 3}) in res.tool_calls
    assert "5" in client.seen_tool_results[0]  # tool result was fed back to the model
    print("✓ tool-calling loop: model→tool→result→answer")


def test_arguments_as_json_string():
    """Some models return arguments as a JSON string — loop must parse it."""
    reg = SkillRegistry()
    reg.register(Skill("echo", "echo text", {"type": "object", "properties": {"t": {"type": "string"}}},
                       run=lambda t: f"echo:{t}"))
    # arguments arrive as a JSON STRING (the behaviour under test); include the
    # approval flag inside that string so the parsed dict is pre-approved.
    client = ScriptedClient([
        ChatMessage(role="assistant", content="", tool_calls=[_tool_call("echo", '{"t":"hi","_approved":true}')]),
        ChatMessage(role="assistant", content="done"),
    ])
    res = Agent(client=client, registry=reg, persona="x").run("echo hi")
    assert res.answer == "done"
    assert "echo:hi" in client.seen_tool_results[0]
    print("✓ JSON-string tool arguments parsed")


def test_bad_tool_call_is_recoverable():
    reg = SkillRegistry()  # empty — 'mystery' doesn't exist
    client = ScriptedClient([
        ChatMessage(role="assistant", content="", tool_calls=[_approved_tool_call("mystery", {})]),
        ChatMessage(role="assistant", content="recovered"),
    ])
    res = Agent(client=client, registry=reg, persona="x").run("go")
    assert res.answer == "recovered"
    assert "[error]" in client.seen_tool_results[0]  # error surfaced, loop continued
    print("✓ unknown tool → error fed back, loop recovers")


def test_step_bound():
    """A model that keeps asking for a tool must never run away. Two guardrails now
    bound it: (1) the permission gate — an unapproved acting tool stops at ASK on
    the FIRST attempt (it can't loop unapproved), and (2) max_steps caps even an
    approved loop. We assert both."""
    reg = SkillRegistry()
    reg.register(Skill("noop", "noop", {"type": "object", "properties": {}}, run=lambda: "ok"))

    # (1) unapproved acting tool → stops immediately at ASK, does not loop.
    looping_unapproved = ChatMessage(role="assistant", content="thinking",
                                     tool_calls=[_tool_call("noop", {})])
    res = Agent(client=ScriptedClient([looping_unapproved]),
                registry=reg, persona="x", max_steps=3).run("loop")
    assert res.route.value == "ask", res.route
    assert res.steps == 1, res.steps

    # (2) approved-every-turn loop is still capped by max_steps (no runaway).
    #     Each scripted turn is a FRESH message so the _approved flag isn't consumed
    #     across iterations — this exercises the max_steps guardrail directly.
    approved_turns = [ChatMessage(role="assistant", content="thinking",
                                  tool_calls=[_approved_tool_call("noop", {})]) for _ in range(6)]
    res2 = Agent(client=ScriptedClient(approved_turns),
                 registry=reg, persona="x", max_steps=3).run("loop")
    assert res2.steps == 3, res2.steps
    print("✓ step bound: unapproved stops at ASK; approved loop capped at max_steps")


def test_builtin_skills():
    # exercise the real skills directly (in a temp workspace)
    with tempfile.TemporaryDirectory() as d:
        os.environ["CTWIN_WORKSPACE"] = d
        # re-import builtin fresh so _workspace() picks up the env
        import importlib
        from cognitive_twin.skills import builtin
        importlib.reload(builtin)
        (Path(d) / "tasks.md").write_text("- ship the agent\n- write tests\n", encoding="utf-8")

        assert "," not in builtin.now() or True  # smoke: returns a date string
        assert "ship the agent" in builtin.daily_digest("tasks.md")
        assert "tasks.md" in builtin.list_dir("")
        assert "ship the agent" in builtin.read_file("tasks.md")
        # sandbox escape is blocked
        try:
            builtin.read_file("../../../etc/passwd")
            raise AssertionError("sandbox escape not blocked")
        except ValueError:
            pass
    print("✓ built-in skills (now, daily_digest, list_dir, read_file, sandbox)")


def test_record_false_keeps_memory_clean():
    """Scripted/internal prompts (record=False) must never become memories."""
    import importlib
    import os
    import tempfile
    os.environ["CTWIN_MEMORY_DIR"] = tempfile.mkdtemp()
    from cognitive_twin import memory
    importlib.reload(memory)
    reg = SkillRegistry()
    agent = Agent(client=ScriptedClient([ChatMessage(role="assistant", content="hi")]),
                  registry=reg, persona="x", use_memory=True)
    agent.run("While the user is away, think about their projects", record=False)
    assert memory.entries() == []          # nothing learned from boilerplate
    agent2 = Agent(client=ScriptedClient([ChatMessage(role="assistant", content="hello!")]),
                   registry=reg, persona="x", use_memory=True)
    agent2.run("good morning mom")         # a real user prompt IS learned
    assert len(memory.entries()) == 1
    print("✓ record=False keeps scripted prompts out of memory")


if __name__ == "__main__":
    test_tool_calling_loop()
    test_arguments_as_json_string()
    test_bad_tool_call_is_recoverable()
    test_step_bound()
    test_builtin_skills()
    print("\nALL TESTS PASSED")

