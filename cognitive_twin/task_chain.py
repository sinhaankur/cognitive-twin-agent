"""
task_chain — Vera turns a goal into an ordered plan, then works it step by step.

"Plan my week", "get the house ready for guests", "ship the landing page" — a goal
that needs several moves, not one. This holds the plan as a checklist, advances it
one step at a time, and reports where things stand. It is the thin orchestration
layer; the STEPS themselves run through the normal agent + its permission gate, so
nothing acts without the same confirm the rest of Vera uses.

Design boundaries (match Vera's posture, keep the backbone simple):
  • PLAN freely; ACT only through the existing gated tools. A chain never invents
    a capability — a step is either a thing the user does, or a tool call the agent
    makes under the usual confirm.
  • GROUNDED: steps are concrete and honest; unknowns are posed as questions, not
    filled with fiction.
  • The plan is SEALED on-device (one per goal), resumable, and the user is always
    in the loop — advance, skip, or stop at any step.

Flow:
    start(goal, steps)  → seal a new checklist
    current()           → the step she's on (to do / confirm with the user)
    advance(note="")    → mark the current step done, move to the next
    skip(note="")       → skip the current step
    status()            → a human read of progress
    stop()              → end the chain

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from . import security

_STORE = "task_chain.json"          # the active chain, sealed on-device
_MAX_STEPS = 12                      # a bounded plan — not an endless backlog


@dataclass
class Step:
    text: str
    kind: str = "do"                 # "do" (user acts) | "ask" (needs a decision) | "auto" (a safe tool)
    done: bool = False
    skipped: bool = False
    note: str = ""


@dataclass
class Chain:
    goal: str
    steps: list[Step] = field(default_factory=list)
    started: float = field(default_factory=time.time)
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal, "started": self.started, "active": self.active,
            "steps": [vars(s) for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Chain":
        steps = [Step(**{k: s.get(k) for k in ("text", "kind", "done", "skipped", "note")})
                 for s in d.get("steps", []) if isinstance(s, dict)]
        return cls(goal=d.get("goal", ""), steps=steps,
                   started=d.get("started", time.time()), active=d.get("active", True))

    def current_index(self) -> int:
        for i, s in enumerate(self.steps):
            if not s.done and not s.skipped:
                return i
        return -1

    def progress(self) -> tuple[int, int]:
        done = sum(1 for s in self.steps if s.done or s.skipped)
        return done, len(self.steps)


# ── persistence (sealed) ───────────────────────────────────────────────────────
def _load() -> Chain | None:
    d = security.read_state(security.path(_STORE), default=None)
    if not isinstance(d, dict) or not d.get("goal"):
        return None
    try:
        return Chain.from_dict(d)
    except Exception:
        return None


def _save(chain: Chain | None) -> None:
    security.write_state(security.path(_STORE), chain.to_dict() if chain else {})


# ── lifecycle ──────────────────────────────────────────────────────────────────
def start(goal: str, steps: list[dict | str]) -> str:
    """Begin a new chain from a goal and an ordered list of steps. A step is a plain
    string (defaults to a 'do'), or {text, kind}. Seals the plan and returns the
    first step to work on."""
    goal = (goal or "").strip()
    if not goal:
        return "What's the goal? Tell me what you want to get done and I'll lay out the steps."
    norm: list[Step] = []
    for s in (steps or [])[:_MAX_STEPS]:
        if isinstance(s, str):
            norm.append(Step(text=s.strip()))
        elif isinstance(s, dict) and s.get("text"):
            kind = s.get("kind") if s.get("kind") in ("do", "ask", "auto") else "do"
            norm.append(Step(text=str(s["text"]).strip(), kind=kind))
    if not norm:
        return f"Got the goal — “{goal}” — but no steps yet. What's the first move?"
    chain = Chain(goal=goal, steps=norm)
    _save(chain)
    first = chain.steps[0]
    return (f"Okay — “{goal}”. Here's the plan ({len(norm)} steps). "
            f"First up: {first.text}")


def current() -> dict[str, Any] | None:
    """The step she's on right now (or None if there's no active chain / it's done)."""
    chain = _load()
    if not chain or not chain.active:
        return None
    i = chain.current_index()
    if i < 0:
        return None
    s = chain.steps[i]
    done, total = chain.progress()
    return {"goal": chain.goal, "index": i, "total": total, "done": done,
            "text": s.text, "kind": s.kind}


def advance(note: str = "") -> str:
    """Mark the current step done and move to the next. Finishes the chain when the
    last step is complete."""
    chain = _load()
    if not chain or not chain.active:
        return "No active plan right now. Want to start one?"
    i = chain.current_index()
    if i < 0:
        chain.active = False
        _save(chain)
        return f"That was the last of it — “{chain.goal}” is done. Nicely handled."
    chain.steps[i].done = True
    chain.steps[i].note = note.strip()
    _save(chain)
    nxt = chain.current_index()
    if nxt < 0:
        chain.active = False
        _save(chain)
        done, total = chain.progress()
        return f"Done — that completes “{chain.goal}” ({total} steps). Nicely handled."
    done, total = chain.progress()
    return f"✓ step {i + 1} done. Next ({done + 1}/{total}): {chain.steps[nxt].text}"


def skip(note: str = "") -> str:
    chain = _load()
    if not chain or not chain.active:
        return "No active plan to skip a step in."
    i = chain.current_index()
    if i < 0:
        return "Nothing left to skip — the plan's complete."
    chain.steps[i].skipped = True
    chain.steps[i].note = note.strip()
    _save(chain)
    nxt = chain.current_index()
    if nxt < 0:
        chain.active = False
        _save(chain)
        return f"Skipped the last step — “{chain.goal}” is wrapped up."
    return f"Skipped. Next: {chain.steps[nxt].text}"


def stop() -> str:
    chain = _load()
    if not chain or not chain.active:
        return "No active plan to stop."
    chain.active = False
    _save(chain)
    return f"Stopped the plan for “{chain.goal}”. We can pick it up again whenever."


def status() -> str:
    """A human read of where the plan stands — the checklist with ticks."""
    chain = _load()
    if not chain or not chain.active:
        return "No plan on the go right now."
    done, total = chain.progress()
    lines = [f"Plan: {chain.goal}  ({done}/{total} done)"]
    cur = chain.current_index()
    for i, s in enumerate(chain.steps):
        mark = "✓" if s.done else ("–" if s.skipped else ("▶" if i == cur else "·"))
        tail = f"  ({s.note})" if s.note else ""
        lines.append(f"  {mark} {s.text}{tail}")
    return "\n".join(lines)


def context_for_prompt() -> str:
    """A short system-prompt note so the model knows a plan is in progress and what
    the current step is — keeps a multi-turn chain coherent. Empty when none."""
    c = current()
    if not c:
        return ""
    return ("# A PLAN IS IN PROGRESS (task chain)\n"
            f"- goal: {c['goal']}\n"
            f"- step {c['index'] + 1} of {c['total']}: {c['text']}\n"
            "Help them with THIS step; when it's done, call it and move on. One step "
            "at a time, their pace — never race ahead or act without their ok.")
