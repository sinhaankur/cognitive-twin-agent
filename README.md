# Cognitive Twin

A local-first personal AI agent that runs entirely on your own machine via
[Ollama](https://ollama.com). It loads a persona, reasons with a local model, and
calls **skills** (tools) to actually do things — get the date, read your notes,
build a digest of your day — with no cloud dependency.

Inspired by [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) ("Personal AI,
on personal devices"). This is an original implementation — same spirit, my code.

> Status: working MVP — model + skills + a bounded tool-calling agent loop + CLI.
> Open source (MIT). The `src/` tree holds earlier scaffolding (OAuth connectors,
> IPC, menubar, multimodal) kept as future layers; the runnable agent is the
> `cognitive_twin/` package.

## Why

Local models already handle a large share of everyday queries. The gap is the
*software around them*: a persona, a skill system, and a reliable loop that turns
"do X" into real actions — locally, privately, on hardware you own.

## Quick start

```bash
# 1. install Ollama (https://ollama.com) and pull a tool-capable model
ollama pull qwen2.5:3b        # or llama3.2, etc.

# 2. run the agent (no Python deps needed for the core)
python -m cognitive_twin "what's the date?"
python -m cognitive_twin "summarize my day"      # uses the daily_digest skill
python -m cognitive_twin                          # interactive REPL
python -m cognitive_twin --skills                 # list available skills
python -m cognitive_twin --model llama3.2 "..."   # choose a model
```

Put a `tasks.md` in your workspace (`~/.cognitive-twin/workspace/`, override with
`CTWIN_WORKSPACE`) and `daily_digest` folds it into the summary. Drop a `.ics`
file there for today's calendar events (no OAuth needed).

## How it works

```
cognitive_twin/
  llm/ollama_client.py   local model over Ollama's HTTP API (stdlib only)
  skills/base.py         Skill contract + registry → tool specs
  skills/builtin.py      now · list_dir · read_file (sandboxed) · daily_digest
  agent/loop.py          persona + tools → model → run tool → feed back → repeat
  cli.py                 one-shot + REPL entrypoint
```

The loop is **bounded** (a step limit) and skills never crash it (errors are fed
back to the model to recover) — deterministic guardrails over an autonomous loop.
Persona comes from `system_dna.md`.

## Adding a skill

```python
from cognitive_twin.skills.base import default_registry as R

@R.add("weather", "Get the weather for a city.",
       {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]})
def weather(city: str) -> str:
    return f"It's pleasant in {city}."   # call a real API here
```

## Configuration

`agent_config.json` (or env): `model`, `host`. Env overrides:
`CTWIN_MODEL`, `CTWIN_OLLAMA_HOST`, `CTWIN_WORKSPACE`.

## Tests

```bash
python -m pytest tests/ -q     # or: python tests/test_agent_loop.py
```

The suite drives the agent loop with a mock model client (no live Ollama needed)
to prove the tool-calling plumbing; live runs use the commands above.

## License

MIT — see [LICENSE](./LICENSE).
