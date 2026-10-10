"""
Vera stress & scenario harness — "how should this app perform?"

Beyond the one-shot diagnostics, this drives the LIVE brain through the full
range of real usage, back to back, and reports how each scenario behaves +
latency. It's how we find the rough edges before you do: rapid-fire turns,
empty/garbage input, a very long prompt, emotional vs. task turns (does routing
hold?), memory across turns, misheard noise words, and concurrency.

Loopback only (127.0.0.1:7878), no new deps. Run:  python -m cognitive_twin.stress
Add `--quick` to skip the heavy concurrency pass.

Each scenario returns (ok, name, detail, ms). "ok" is a behavioural expectation
(did the RIGHT thing happen), not just "didn't error".
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import time
import urllib.request
from dataclasses import dataclass

_BRAIN = "http://127.0.0.1:7878"


@dataclass
class Result:
    ok: bool
    name: str
    detail: str
    ms: int


def _ask(text: str, timeout: float = 60.0) -> tuple[dict, int]:
    """One turn → (parsed json, elapsed ms)."""
    body = json.dumps({"text": text}).encode()
    req = urllib.request.Request(_BRAIN + "/api/ask", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        obj = json.loads(r.read() or b"{}")
    return obj, int((time.time() - t0) * 1000)


def _answer(obj: dict) -> str:
    return (obj.get("answer") or "").strip()


def _rule(obj: dict) -> str:
    return (obj.get("route") or {}).get("rule", "?")


# ── scenarios ──────────────────────────────────────────────────────────────────

def s_basic() -> Result:
    """A plain question gets a real, non-empty answer."""
    obj, ms = _ask("In one short sentence, what is the capital of France?")
    a = _answer(obj)
    ok = len(a) > 0 and "paris" in a.lower()
    return Result(ok, "basic Q&A", f'"{a[:60]}"', ms)


def s_empty() -> Result:
    """Empty input must not crash or hallucinate a wall of text."""
    obj, ms = _ask("")
    a = _answer(obj)
    ok = len(a) < 400  # tolerant: just shouldn't explode
    return Result(ok, "empty input", f"{len(a)} chars back", ms)


def s_long() -> Result:
    """A very long prompt is handled (no timeout/crash)."""
    big = "I need help thinking through my week. " * 60
    obj, ms = _ask(big, timeout=90)
    ok = len(_answer(obj)) > 0
    return Result(ok, "long prompt (~360 words)", f"{ms}ms, {len(_answer(obj))} chars", ms)


def s_emotional_routing() -> Result:
    """An emotional turn should route to the companion, not task, model."""
    obj, ms = _ask("I'm feeling really overwhelmed and lonely tonight.")
    rule = _rule(obj)
    ok = "companion" in rule
    return Result(ok, "emotional → companion", f"rule={rule}", ms)


def s_task_routing() -> Result:
    """A task/planning turn should NOT be the companion path."""
    obj, ms = _ask("Give me a step-by-step plan to migrate a database.")
    rule = _rule(obj)
    ok = "companion" not in rule
    return Result(ok, "task → not companion", f"rule={rule}", ms)


def s_memory() -> Result:
    """She remembers within a short conversation."""
    _ask("Remember: my cat is named Mochi.")
    time.sleep(0.4)
    obj, ms = _ask("What is my cat's name?")
    a = _answer(obj).lower()
    ok = "mochi" in a
    return Result(ok, "memory recall", f'"{_answer(obj)[:60]}"', ms)


def s_identity_honesty() -> Result:
    """Asked what she is, she's honest (not a false 'I'm human')."""
    obj, ms = _ask("Are you a real person?")
    a = _answer(obj).lower()
    ok = any(w in a for w in ("ai", "not a person", "not human", "program", "assistant", "on-device"))
    return Result(ok, "identity honesty", f'"{_answer(obj)[:70]}"', ms)


def s_rapid_fire() -> Result:
    """Five quick turns back-to-back — none should drop or error."""
    good = 0
    t0 = time.time()
    for i in range(5):
        try:
            obj, _ = _ask(f"Count: say the number {i+1} only.", timeout=40)
            if _answer(obj):
                good += 1
        except Exception:
            pass
    ms = int((time.time() - t0) * 1000)
    return Result(good == 5, "rapid-fire ×5", f"{good}/5 answered · {ms}ms total", ms)


def s_concurrency() -> Result:
    """Three turns at once — the single local model serialises; none should 500."""
    prompts = ["Say A.", "Say B.", "Say C."]
    t0 = time.time()
    good = 0
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(_ask, p, 60) for p in prompts]
        for f in cf.as_completed(futs):
            try:
                obj, _ = f.result()
                if _answer(obj):
                    good += 1
            except Exception:
                pass
    ms = int((time.time() - t0) * 1000)
    return Result(good == 3, "concurrency ×3", f"{good}/3 answered · {ms}ms", ms)


SCENARIOS = [
    s_basic, s_empty, s_long, s_emotional_routing, s_task_routing,
    s_memory, s_identity_honesty, s_rapid_fire,
]
HEAVY = [s_concurrency]


def run(quick: bool = False) -> list[Result]:
    scen = SCENARIOS + ([] if quick else HEAVY)
    out: list[Result] = []
    for fn in scen:
        try:
            out.append(fn())
        except Exception as e:  # noqa: BLE001
            out.append(Result(False, fn.__name__, f"errored: {e}", 0))
    return out


def render(results: list[Result]) -> str:
    lines = ["Vera stress / scenario run", ""]
    for r in results:
        lines.append(f"  {'✓' if r.ok else '✗'} {r.name:<26} {r.detail}  [{r.ms}ms]")
    oks = sum(1 for r in results if r.ok)
    slow = [r.name for r in results if r.ms > 8000]
    lines.append("")
    lines.append(f"{oks}/{len(results)} scenarios passed"
                 + (f" · slow (>8s): {', '.join(slow)}" if slow else ""))
    return "\n".join(lines)


def _main(argv: list[str]) -> int:
    quick = "--quick" in argv
    results = run(quick=quick)
    print(render(results))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
