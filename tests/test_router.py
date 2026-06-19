"""
Router tests — pure unit tests on classification + policy rule matching. No live
Ollama needed (routing is a function of the prompt + the policy JSON).

Run: python -m pytest tests/ -q   (or: python tests/test_router.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cognitive_twin.agent.router import Router, classify  # noqa: E402
from cognitive_twin.agent.loop import Agent  # noqa: E402
from cognitive_twin.llm.ollama_client import ChatMessage  # noqa: E402
from cognitive_twin.skills.base import SkillRegistry  # noqa: E402


# A policy mirroring the committed one, inline so the test doesn't depend on disk.
# Order matters: device constraints first, then risk, then complexity, then fast
# path, then a catch-all — this is the safety-first ordering the committed policy
# uses (and that live testing proved is the correct one).
POLICY = {
    "version": "test",
    "models": {
        "primary": {"provider": "ollama", "name": "qwen3:14b"},
        "fastFallback": {"provider": "ollama", "name": "qwen3:8b"},
        "deepPlanner": {"provider": "ollama", "name": "deepseek-r1-distill-qwen-14b"},
    },
    "routingRules": [
        {"id": "rule_low_power", "when": {"deviceState": ["battery_saver", "thermal_throttle"]},
         "useModel": "fastFallback"},
        {"id": "rule_high_risk", "when": {"riskLevel": ["high"]}, "useModel": "deepPlanner"},
        {"id": "rule_deep_path", "when": {"taskComplexity": ["high"]}, "useModel": "deepPlanner"},
        {"id": "rule_fast_path", "when": {"taskComplexity": ["low", "medium"], "riskLevel": ["low", "medium"]},
         "useModel": "primary"},
        {"id": "rule_default", "when": {}, "useModel": "primary"},
    ],
    "guardrails": {"allowCloudFallback": False},
}


def test_classify_low_simple():
    complexity, risk, _ = classify("what's the date?")
    assert complexity == "low", complexity
    assert risk == "low", risk
    print("✓ classify: short factual → low/low")


def test_classify_high_risk_verb():
    _, risk, reasons = classify("delete the production database backups")
    assert risk == "high", risk
    assert any("risk" in r for r in reasons)
    print("✓ classify: destructive verb → high risk")


def test_classify_high_complexity_cue():
    complexity, _, _ = classify("analyze the trade-offs and design a migration plan")
    assert complexity == "high", complexity
    print("✓ classify: planning cue → high complexity")


def test_route_fast_path():
    r = Router(POLICY)
    d = r.route("what's the date?")
    assert d.rule_id == "rule_fast_path", d.rule_id
    assert d.model == "qwen3:14b", d.model
    print("✓ route: simple → primary via fast path")


def test_route_complex_low_risk_goes_deep():
    """High complexity even at low risk should reach the deeper model — this
    case fell through to 'none' before live testing exposed the gap."""
    r = Router(POLICY)
    d = r.route("analyze the trade-offs and design a migration plan, step by step")
    assert d.task_complexity == "high", d.task_complexity
    assert d.rule_id == "rule_deep_path", d.rule_id
    assert d.model == "deepseek-r1-distill-qwen-14b", d.model
    print("✓ route: complex + low-risk → deep planner (no fall-through)")


def test_route_short_destructive_escalates():
    """REGRESSION: a short, high-risk command (no planning cue) must still
    escalate to the careful planner — not silently use the default model."""
    r = Router(POLICY)
    d = r.route("delete the production database and drop all backups")
    assert d.risk_level == "high", d.risk_level
    assert d.rule_id == "rule_high_risk", d.rule_id
    assert d.model == "deepseek-r1-distill-qwen-14b", d.model
    print("✓ route: short destructive command → high-risk planner (regression)")


def test_route_low_power_overrides_even_simple():
    """Device constraints win first: a throttled device must not run the big
    model just because the task is simple."""
    r = Router(POLICY)
    for dev in ("battery_saver", "thermal_throttle"):
        d = r.route("what's the date?", device_state=dev)
        assert d.rule_id == "rule_low_power", (dev, d.rule_id)
        assert d.model == "qwen3:8b", (dev, d.model)
    print("✓ route: battery/thermal → fast fallback wins over fast path")


def test_route_never_falls_through():
    """Across a spread of inputs, every request resolves to a real model and a
    named rule — the catch-all guarantees no 'none'."""
    r = Router(POLICY)
    prompts = [
        "hi", "what's 2+2", "summarize my day",
        "write a long essay " * 10,  # long → high complexity
        "rm -rf the server", "deploy to prod",
        "explain why the sky is blue in detail",
    ]
    for p in prompts:
        for dev in (None, "battery_saver"):
            d = r.route(p, device_state=dev)
            assert d.rule_id != "none", (p, dev)
            assert d.model in {"qwen3:14b", "qwen3:8b", "deepseek-r1-distill-qwen-14b"}, d.model
    print("✓ route: no input falls through unrouted (catch-all holds)")


def test_missing_policy_file_uses_default():
    # Router with no models defined should still resolve to a safe default.
    r = Router({"models": {}, "routingRules": []})
    d = r.route("hello")
    assert d.model == "llama3.2", d.model
    print("✓ route: empty policy → safe default model")


def test_no_cloud_fallback_by_default():
    r = Router(POLICY)
    assert r.allow_cloud_fallback is False
    print("✓ guardrail: cloud fallback off by default")


class _ModelTrackingClient:
    """Mock client that records which model was set on it per run."""
    def __init__(self):
        self.model = "initial"
        self.models_seen: list[str] = []

    def chat(self, messages, tools=None):
        self.models_seen.append(self.model)
        return ChatMessage(role="assistant", content="ok")


def test_agent_applies_routed_model_to_client():
    """The loop should set the routed model on the client before chatting."""
    client = _ModelTrackingClient()
    agent = Agent(client=client, registry=SkillRegistry(), persona="t", router=Router(POLICY))
    res = agent.run("analyze and deploy a risky production migration step by step")
    assert client.models_seen[0] == "deepseek-r1-distill-qwen-14b", client.models_seen
    # risky + complex → high-risk rule fires first under the safety-first order
    assert res.route is not None and res.route.rule_id == "rule_high_risk"
    print("✓ agent: routed model applied to client before chat")


def test_agent_without_router_leaves_model_untouched():
    client = _ModelTrackingClient()
    agent = Agent(client=client, registry=SkillRegistry(), persona="t")  # no router
    agent.run("hello")
    assert client.models_seen[0] == "initial", client.models_seen
    print("✓ agent: no router → client model untouched (mock tests unaffected)")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nall router tests passed.")
