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


def build_agent(model: str | None = None) -> Agent:
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
    return Agent(client=client, registry=default_registry)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ctwin", description="Local-first personal AI agent.")
    ap.add_argument("prompt", nargs="*", help="one-shot prompt; omit for an interactive REPL")
    ap.add_argument("--model", help="Ollama model (default from config or llama3.2)")
    ap.add_argument("--skills", action="store_true", help="list available skills and exit")
    args = ap.parse_args(argv)

    if args.skills:
        # don't need Ollama just to list skills
        for n in default_registry.names():
            sk = default_registry.get(n)
            print(f"  {n:<14} {sk.description if sk else ''}")
        return 0

    agent = build_agent(args.model)

    # preflight: clear message if the brain isn't reachable
    try:
        agent.client.ensure_ready()  # type: ignore[attr-defined]
    except OllamaError as e:
        print(f"⚠ {e}", file=sys.stderr)
        return 1

    if args.prompt:
        result = agent.run(" ".join(args.prompt))
        print(result.answer)
        return 0

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
        try:
            result = agent.run(line)
            print(result.answer + "\n")
        except OllamaError as e:
            print(f"⚠ {e}\n", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
