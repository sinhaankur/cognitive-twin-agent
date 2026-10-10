"""
plan_skill — turn a goal into a step-by-step plan Vera works through with you.

Wraps task_chain.py as skills the agent can call: start a plan from a goal + steps,
advance/skip the current step, and read where things stand. The STEPS still run
through the normal agent + its permission gate — this is just the orchestration, so
"plan my week" / "get ready for guests" becomes an ordered checklist she walks with
you, one step at a time, your pace. Grounded, on-device, never acts without your ok.

© Ankur Sinha. Personal use.
"""
from __future__ import annotations

from .base import default_registry as R
from .. import task_chain


@R.add(
    "plan_start",
    "Start a step-by-step plan for a goal that needs several moves (e.g. 'plan my "
    "week', 'get the house ready for guests', 'ship the landing page'). Give the "
    "goal and an ordered list of concrete steps; she seals the checklist and begins "
    "the first step. Use when the user asks to plan/organise something multi-step.",
    {"type": "object", "properties": {
        "goal": {"type": "string", "description": "what they want to get done"},
        "steps": {"type": "array", "items": {"type": "string"},
                  "description": "ordered, concrete steps toward the goal"}},
     "required": ["goal", "steps"]},
)
def plan_start(goal: str = "", steps: list | None = None) -> str:
    return task_chain.start(goal, steps or [])


@R.add(
    "plan_next",
    "Mark the current plan step done and move to the next (optionally a short note "
    "on what happened). Use when the user says a step is finished / 'done' / 'next'.",
    {"type": "object", "properties": {
        "note": {"type": "string", "description": "optional note on the step just finished"}}},
)
def plan_next(note: str = "") -> str:
    return task_chain.advance(note)


@R.add(
    "plan_skip",
    "Skip the current plan step and move on (use when the user wants to leave one "
    "out). Optionally a note on why.",
    {"type": "object", "properties": {
        "note": {"type": "string", "description": "optional reason for skipping"}}},
)
def plan_skip(note: str = "") -> str:
    return task_chain.skip(note)


@R.add(
    "plan_status",
    "Show where the current plan stands — the checklist with what's done, the "
    "current step, and what's left. Use when the user asks 'where are we' / 'what's "
    "the plan' / 'what's next'.",
    {"type": "object", "properties": {}},
)
def plan_status() -> str:
    return task_chain.status()


@R.add(
    "plan_stop",
    "Stop / abandon the current plan (it can be picked up later). Use when the user "
    "says to stop, cancel, or drop the plan.",
    {"type": "object", "properties": {}},
)
def plan_stop() -> str:
    return task_chain.stop()
