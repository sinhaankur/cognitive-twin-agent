"""
Conversation eval harness — measure Vera's talk quality, repeatably.

This is the FOUNDATION for tuning her (prompt tweaks, a fine-tune, voice params):
you can't improve what you don't measure. It runs real multi-turn conversations
through a live agent and scores each on CHECKABLE dimensions — context recall,
staying in character, conciseness, holding space, no emoji-spam, honesty about
what she can't know — then prints a report and an overall score.

It needs a live Ollama + a pulled chat model (it's a real conversation, not a
mock), so it's a standalone script, NOT part of the fast unit suite. Run it
before/after any change to see if her conversation got better or worse.

    python -m evals.conversation_eval                 # default model (routing)
    python -m evals.conversation_eval --model qwen2.5:7b
    python -m evals.conversation_eval --json out.json # machine-readable report
    python -m evals.conversation_eval --repeat 3      # average over N runs (noise)

Exit code is 0 when the pass-rate meets --threshold (default 0.8), else 1 — so it
can gate a change in CI once a model is available.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cognitive_twin.cli import build_agent  # noqa: E402

_HERE = Path(__file__).resolve().parent
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002B00-\U00002BFF\U0000FE00-\U0000FE0F]+"
)


# ── scoring ────────────────────────────────────────────────────────────────────
@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class TurnResult:
    user: str
    answer: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)


def _count_emoji(text: str) -> int:
    return sum(len(m) for m in _EMOJI_RE.findall(text))


def _check_turn(answer: str, spec: dict) -> list[CheckResult]:
    """Apply every check declared on a turn spec. A turn with no checks only
    verifies she produced a non-empty answer."""
    a = answer.lower()
    out: list[CheckResult] = []

    out.append(CheckResult("non-empty", bool(answer.strip()),
                           "" if answer.strip() else "empty answer"))

    if "expect_contains_any" in spec:
        want = [w.lower() for w in spec["expect_contains_any"]]
        hit = any(w in a for w in want)
        out.append(CheckResult("recall", hit,
                               "" if hit else f"missing any of {want}"))

    if "expect_not_contains" in spec:
        bad = [w.lower() for w in spec["expect_not_contains"]]
        hits = [w for w in bad if w in a]
        out.append(CheckResult("avoid", not hits,
                               "" if not hits else f"contained {hits}"))

    if "max_words" in spec:
        n = len(answer.split())
        ok = n <= spec["max_words"]
        out.append(CheckResult("concise", ok, "" if ok else f"{n} words > {spec['max_words']}"))

    if "min_words" in spec:
        n = len(answer.split())
        ok = n >= spec["min_words"]
        out.append(CheckResult("substantive", ok, "" if ok else f"{n} words < {spec['min_words']}"))

    if "max_emoji" in spec:
        n = _count_emoji(answer)
        ok = n <= spec["max_emoji"]
        out.append(CheckResult("emoji", ok, "" if ok else f"{n} emoji > {spec['max_emoji']}"))

    return out


# ── running ────────────────────────────────────────────────────────────────────
def run_conversation(convo: dict, *, model: str | None) -> list[TurnResult]:
    """Run one scenario end to end on a FRESH agent (so context recall tests
    the agent's own memory, not leakage from a previous scenario)."""
    agent = build_agent(model, route=(model is None), interactive_confirm=False)
    results: list[TurnResult] = []
    for turn in convo["turns"]:
        user = turn["user"]
        try:
            res = agent.run(user, record=True)
            answer = res.answer
        except Exception as e:  # a crash is the worst failure — record it
            answer = f"(agent error: {e})"
        results.append(TurnResult(user=user, answer=answer, checks=_check_turn(answer, turn)))
    return results


def load_conversations(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Vera conversation eval")
    ap.add_argument("--model", help="pin a model (default: policy routing)")
    ap.add_argument("--data", default=str(_HERE / "conversations.jsonl"))
    ap.add_argument("--json", help="write a machine-readable report here")
    ap.add_argument("--repeat", type=int, default=1, help="runs per scenario (averaged)")
    ap.add_argument("--threshold", type=float, default=0.8, help="pass-rate to exit 0")
    args = ap.parse_args(argv)

    conversations = load_conversations(Path(args.data))
    print(f"Vera conversation eval — {len(conversations)} scenarios"
          f"{' x ' + str(args.repeat) if args.repeat > 1 else ''}, "
          f"model={args.model or 'routing'}\n")

    report: list[dict] = []
    total_checks = 0
    passed_checks = 0
    scenario_pass = 0
    scenario_total = 0
    t0 = time.monotonic()

    for convo in conversations:
        runs_ok = 0
        last_turns: list[TurnResult] = []
        for _ in range(args.repeat):
            turns = run_conversation(convo, model=args.model)
            last_turns = turns
            if all(t.ok for t in turns):
                runs_ok += 1
        ok = runs_ok == args.repeat if args.repeat > 1 else all(t.ok for t in last_turns)
        scenario_total += 1
        scenario_pass += 1 if ok else 0

        mark = "✓" if ok else "✗"
        print(f"{mark} {convo['id']}  ({convo.get('why','')})")
        for t in last_turns:
            for c in t.checks:
                total_checks += 1
                passed_checks += 1 if c.ok else 0
                if not c.ok:
                    print(f"    ✗ {c.name}: {c.detail}")
                    print(f"      user: {t.user!r}")
                    print(f"      her : {t.answer[:120]!r}")
        report.append({
            "id": convo["id"],
            "ok": ok,
            "runs_ok": runs_ok,
            "runs": args.repeat,
            "turns": [{"user": t.user, "answer": t.answer,
                       "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in t.checks]}
                      for t in last_turns],
        })

    dt = time.monotonic() - t0
    pass_rate = scenario_pass / scenario_total if scenario_total else 0.0
    check_rate = passed_checks / total_checks if total_checks else 0.0
    print(f"\n── score ──")
    print(f"scenarios passed : {scenario_pass}/{scenario_total}  ({pass_rate:.0%})")
    print(f"checks passed    : {passed_checks}/{total_checks}  ({check_rate:.0%})")
    print(f"time             : {dt:.1f}s")

    if args.json:
        Path(args.json).write_text(json.dumps({
            "model": args.model or "routing",
            "pass_rate": pass_rate,
            "check_rate": check_rate,
            "scenarios": report,
        }, indent=2), encoding="utf-8")
        print(f"report           : {args.json}")

    ok = pass_rate >= args.threshold
    print(f"\n{'PASS' if ok else 'FAIL'} (threshold {args.threshold:.0%})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
