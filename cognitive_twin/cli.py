"""
Cognitive Twin CLI.

  ctwin "what's the date?"          one-shot
  ctwin                            interactive REPL
  ctwin --model qwen2.5 "..."      pick a model

Reads optional config from agent_config.json (model, host). Imports the built-in
skills so they're registered. Fails clearly if Ollama isn't running / the model
isn't pulled — no cloud fallback (this is local-first by design).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .agent.loop import Agent
from .agent.router import Router
from .llm.ollama_client import OllamaClient, OllamaError
from . import skills  # noqa: F401  (registry exists)
from .skills import builtin  # noqa: F401  (registers built-in skills)
from .skills.base import default_registry


def _load_config() -> dict:
    for p in (Path.cwd() / "agent_config.json", Path.cwd() / "agent_config.example.json"):
        try:
            if p.is_file():
                return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def build_agent(model: str | None = None, *, route: bool = True) -> Agent:
    cfg = _load_config()
    model = (
        model
        or os.environ.get("CTWIN_MODEL")
        or cfg.get("model")
        or cfg.get("llm", {}).get("model")
        or "llama3.2"
    )
    host = os.environ.get("CTWIN_OLLAMA_HOST") or cfg.get("host") or "http://localhost:11434"
    client = OllamaClient(model=model, host=host)
    # Policy-driven routing is on by default — pick a local model per request from
    # policies/model-routing.policy.json. An explicit --model or --no-route turns
    # it off and pins the one model.
    router = Router() if route else None
    agent = Agent(client=client, registry=default_registry, router=router)
    # Remember the configured default so fallback can prefer it over a random
    # installed model (which might not support tool-calling).
    agent.configured_model = model  # type: ignore[attr-defined]
    return agent


# Model families known to support tool/function calling in Ollama. Used to pick a
# sane fallback when the policy's model isn't pulled. Not exhaustive — just a
# preference order over "first installed", which may be a tool-less tiny model.
_TOOL_CAPABLE_HINTS = ("qwen2.5", "qwen3", "llama3.1", "llama3.2", "mistral", "deepseek")


def _choose_fallback(configured: str | None, installed: list[str]) -> str | None:
    """Pick the best installed model to fall back to: the configured default if
    it's present, else a known tool-capable model, else the first installed."""
    if not installed:
        return None
    if configured:
        base = configured.split(":")[0]
        for m in installed:
            if m == configured or m.split(":")[0] == base:
                return m
    for hint in _TOOL_CAPABLE_HINTS:
        for m in installed:
            if m.split(":")[0].startswith(hint):
                return m
    return installed[0]


def _run_once(agent: Agent, prompt: str, explain: bool, *, repl: bool = False) -> bool:
    """Run one prompt. With routing on, if the routed model isn't pulled, pin an
    installed model for this run so the agent still answers — staying local.
    Prints the route when `explain` is set. Returns True on success."""
    suffix = "\n" if repl else ""
    client = agent.client
    pinned: str | None = None  # set when we fall back off the routed model

    if agent.router is not None and hasattr(client, "available_models"):
        decision = agent.router.route(prompt)
        installed = client.available_models()  # type: ignore[attr-defined]
        base = decision.model.split(":")[0]
        have = any(m == decision.model or m.split(":")[0] == base for m in installed)
        if not have and installed:
            configured = getattr(agent, "configured_model", None)
            pinned = _choose_fallback(configured, installed)
            if explain:
                print(
                    f"route · policy wanted {decision.model} ({decision.rule_id}); "
                    f"not pulled → using {pinned}",
                    file=sys.stderr,
                )
        elif explain:
            print(decision.explain(), file=sys.stderr)

    # If we're falling back, pin the model and turn routing off for this one run
    # (so agent.run doesn't re-route over our choice).
    saved_router = None
    if pinned is not None:
        client.model = pinned  # type: ignore[attr-defined]
        saved_router, agent.router = agent.router, None
    try:
        result = agent.run(prompt)
    except OllamaError as e:
        print(f"⚠ {e}{suffix}", file=sys.stderr)
        return False
    finally:
        if saved_router is not None:
            agent.router = saved_router

    print(result.answer + suffix)
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ctwin", description="Local-first personal AI agent.")
    ap.add_argument("prompt", nargs="*", help="one-shot prompt; omit for an interactive REPL")
    ap.add_argument("--model", help="Ollama model — pins this model and disables routing")
    ap.add_argument("--skills", action="store_true", help="list available skills and exit")
    ap.add_argument("--no-route", action="store_true", help="disable policy routing; use one model")
    ap.add_argument(
        "--route-explain", action="store_true",
        help="print which model/rule the policy picked for each request",
    )
    args = ap.parse_args(argv)

    if args.skills:
        # don't need Ollama just to list skills
        for n in default_registry.names():
            sk = default_registry.get(n)
            print(f"  {n:<14} {sk.description if sk else ''}")
        return 0

    # An explicit --model pins one model (routing off); otherwise route by policy.
    use_routing = not args.no_route and not args.model
    agent = build_agent(args.model, route=use_routing)
    explain = args.route_explain

    # preflight: clear message if the brain isn't reachable. With routing on, the
    # model is chosen per request, so only require the server to be up here; a
    # routed model that isn't pulled is handled per-run with a graceful fallback.
    client = agent.client  # type: ignore[assignment]
    try:
        if use_routing:
            if not client.is_up():  # type: ignore[attr-defined]
                raise OllamaError("Ollama isn't running. Start it with `ollama serve`, then try again.")
        else:
            client.ensure_ready()  # type: ignore[attr-defined]
    except OllamaError as e:
        print(f"⚠ {e}", file=sys.stderr)
        return 1

    if args.prompt:
        return 0 if _run_once(agent, " ".join(args.prompt), explain) else 1

    # REPL
    print("Cognitive Twin · local agent. Ctrl-D or 'exit' to quit.\n")
    while True:
        try:
            line = input("» ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line in {"exit", "quit"}:
            return 0
        if not line:
            continue
        _run_once(agent, line, explain, repl=True)


if __name__ == "__main__":
    raise SystemExit(main())
