"""
Policy-driven model routing — local-first, by rule.

The thesis (shared with local-first agent research like OpenJarvis): keep work on
device and pick the *right local model* for the job instead of sending everything
to one big model — or to the cloud. The routing policy lives in
``policies/model-routing.policy.json`` and is data, not code, so it can change
without touching the loop.

This module:
  1. loads that policy (with a sane built-in default if it's missing),
  2. classifies a request into ``taskComplexity`` + ``riskLevel`` with a small,
     transparent heuristic — no extra model call, stdlib only,
  3. matches the policy's ``routingRules`` in order and returns the chosen model.

The classifier is deliberately a heuristic, not a learned policy: it's honest,
inspectable, and cheap. Swapping in a learned classifier later is a drop-in.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# --- default policy: used only if policies/model-routing.policy.json is absent.
# Mirrors the shape of the committed policy so behaviour is predictable offline.
_DEFAULT_POLICY: dict[str, Any] = {
    "version": "0-default",
    "models": {
        "primary": {"provider": "ollama", "name": "qwen2.5:7b", "role": "default_reasoning"},
    },
    "routingRules": [
        {"id": "rule_default", "when": {}, "useModel": "primary"},
    ],
    "guardrails": {"allowCloudFallback": False},
}


# Keywords that nudge the heuristic. Kept small and readable on purpose — this is
# a starting signal, not a classifier pretending to be more than it is.
_HIGH_RISK = re.compile(
    r"\b(delete|remove|drop|deploy|migrat|overwrit|rm\s|sudo|push|force|"
    r"production|prod\b|credential|password|secret|payment|transfer|wipe|reset)\b",
    re.IGNORECASE,
)
_HIGH_COMPLEXITY = re.compile(
    r"\b(plan|architect|design|analy[sz]e|compare|trade-?off|strateg|"
    r"why|debug|root cause|refactor|multi-?step|step by step|reason)\b",
    re.IGNORECASE,
)


@dataclass
class RouteDecision:
    """The outcome of routing one request."""
    model: str                       # the resolved Ollama model name
    model_key: str                   # which entry in policy.models was chosen
    rule_id: str                     # which routing rule fired
    task_complexity: str             # low | medium | high
    risk_level: str                  # low | medium | high
    device_state: str | None = None  # e.g. battery_saver, if signalled
    reasons: list[str] = field(default_factory=list)

    def explain(self) -> str:
        bits = [
            f"model={self.model} ({self.model_key})",
            f"rule={self.rule_id}",
            f"complexity={self.task_complexity}",
            f"risk={self.risk_level}",
        ]
        if self.device_state:
            bits.append(f"device={self.device_state}")
        line = "route · " + " · ".join(bits)
        if self.reasons:
            line += "\n        " + "; ".join(self.reasons)
        return line


def load_policy(path: Path | None = None) -> dict[str, Any]:
    """Load the routing policy JSON, falling back to a safe default."""
    candidates = (
        [path] if path is not None else [
            Path(__file__).resolve().parents[2] / "policies" / "model-routing.policy.json",
            Path.cwd() / "policies" / "model-routing.policy.json",
        ]
    )
    for p in candidates:
        try:
            if p and p.is_file():
                return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # a broken policy file should degrade to default, not crash the agent
            pass
    return _DEFAULT_POLICY


# Emotional / companionship cues — route these to the warm companion model. Kept
# narrow on purpose: a genuine feeling/check-in turn, NOT anything with a task in
# it (reasoning cues below always win, so "I'm stressed, help me plan X" reasons).
_COMPANION = re.compile(
    r"\b(feel(ing)?|lonely|overwhelmed|anxious|sad|tired|exhausted|stressed|"
    r"miss you|talk to me|just talk|check in|how are you|comfort|vent|"
    r"proud of me|cheer me)\b",
    re.IGNORECASE,
)


def classify(prompt: str) -> tuple[str, str, str, list[str]]:
    """Heuristically estimate (taskComplexity, riskLevel, intent, reasons).

    Transparent by design: length + a few keyword cues. Returns the reasons so
    the decision is inspectable (``--route-explain``).
    """
    reasons: list[str] = []
    text = prompt.strip()
    words = len(text.split())

    # risk
    if _HIGH_RISK.search(text):
        risk = "high"
        reasons.append("matched a high-risk verb (e.g. delete/deploy/secret)")
    else:
        risk = "low"

    # complexity — long prompts or reasoning cues lean higher
    if words >= 60 or _HIGH_COMPLEXITY.search(text):
        complexity = "high"
        reasons.append(
            "reasoning/planning cue or long prompt" if words >= 60 else "matched a reasoning/planning cue"
        )
    elif words >= 18:
        complexity = "medium"
        reasons.append("medium-length request")
    else:
        complexity = "low"

    # intent — companion ONLY when there's an emotional cue AND no reasoning/task
    # cue and it's not a high-complexity/high-risk turn (those need a real brain).
    if (
        _COMPANION.search(text)
        and not _HIGH_COMPLEXITY.search(text)
        and complexity != "high"
        and risk == "low"
    ):
        intent = "companion"
        reasons.append("emotional/check-in cue → companion")
    else:
        intent = "task"

    return complexity, risk, intent, reasons


def _device_state() -> str | None:
    """Optional device hint via env, honouring the policy's low-power rule.
    e.g. CTWIN_DEVICE_STATE=battery_saver | thermal_throttle | normal
    """
    val = (os.environ.get("CTWIN_DEVICE_STATE") or "").strip().lower()
    return val or None


_KNOWN_CONDITIONS = {"taskComplexity", "riskLevel", "deviceState", "intent"}


def _rule_matches(
    when: dict[str, Any], complexity: str, risk: str, device: str | None, intent: str
) -> bool:
    """A rule matches if every condition it specifies is satisfied. An empty
    ``when`` is a catch-all. A rule that references a condition the router does
    NOT understand can never match — otherwise an unknown key would be silently
    ignored and the rule would behave like a catch-all (the bug that sent every
    request to the companion model)."""
    if not when:
        return True
    if any(k not in _KNOWN_CONDITIONS for k in when):
        return False
    if "taskComplexity" in when and complexity not in when["taskComplexity"]:
        return False
    if "riskLevel" in when and risk not in when["riskLevel"]:
        return False
    if "intent" in when and intent not in when["intent"]:
        return False
    if "deviceState" in when:
        if device is None or device not in when["deviceState"]:
            return False
    return True


class Router:
    """Resolves a request to a local model using the routing policy."""

    def __init__(self, policy: dict[str, Any] | None = None) -> None:
        self.policy = policy or load_policy()

    @property
    def allow_cloud_fallback(self) -> bool:
        return bool(self.policy.get("guardrails", {}).get("allowCloudFallback", False))

    def _resolve_model_name(self, model_key: str) -> tuple[str, str]:
        """Map a policy model key (e.g. 'primary') to its concrete name. Falls
        back to the first defined model, then to an installed safe default."""
        models = self.policy.get("models", {})
        entry = models.get(model_key)
        if entry and entry.get("name"):
            return model_key, entry["name"]
        # key not found — use the first model in the policy, else a safe default
        for k, v in models.items():
            if v.get("name"):
                return k, v["name"]
        return "default", "qwen2.5:7b"

    def route(self, prompt: str, *, device_state: str | None = None) -> RouteDecision:
        complexity, risk, intent, reasons = classify(prompt)
        device = device_state if device_state is not None else _device_state()

        chosen_key = None
        fired_rule = "none"
        for rule in self.policy.get("routingRules", []):
            if _rule_matches(rule.get("when", {}), complexity, risk, device, intent):
                chosen_key = rule.get("useModel")
                fired_rule = rule.get("id", "unnamed")
                break

        if chosen_key is None:
            # no rule matched — fall back to the first model, note it
            reasons.append("no routing rule matched; used the first policy model")
            chosen_key = next(iter(self.policy.get("models", {})), "primary")

        model_key, model_name = self._resolve_model_name(chosen_key)
        return RouteDecision(
            model=model_name,
            model_key=model_key,
            rule_id=fired_rule,
            task_complexity=complexity,
            risk_level=risk,
            device_state=device,
            reasons=reasons,
        )
