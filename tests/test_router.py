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
        {"id": "rule_deep_path", "when": {"taskComplexity": ["high"], "riskLevel": ["medium", "high"]},
         "useModel": "deepPlanner"},
        {"id": "rule_fast_path", "when": {"taskComplexity": ["low", "medium"], "riskLevel": ["low"]},
         "useModel": "primary"},
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


def test_route_deep_path():
    r = Router(POLICY)
    d = r.route("plan and deploy a risky migration to production, step by step")
    # high complexity (plan/step by step) + high risk (deploy/production) → deep
    assert d.rule_id == "rule_deep_path", d.rule_id
    assert d.model == "deepseek-r1-distill-qwen-14b", d.model
    print("✓ route: complex + risky → deep planner")


def test_route_low_power_overrides():
    r = Router(POLICY)
    d = r.route("what's the date?", device_state="battery_saver")
    assert d.rule_id == "rule_low_power", d.rule_id
    assert d.model == "qwen3:8b", d.model
    print("✓ route: battery_saver → fast fallback (low-power rule wins)")


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
    assert res.route is not None and res.route.rule_id == "rule_deep_path"
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
