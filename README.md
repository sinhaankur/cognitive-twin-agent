# Cognitive Twin

A local-first personal AI agent that runs entirely on your own machine via
[Ollama](https://ollama.com). It loads a persona, reasons with a local model, and
calls **skills** (tools) to actually do things — get the date, read your notes,
build a digest of your day — with no cloud dependency.

Inspired by [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) ("Personal AI,
on personal devices"). This is an original implementation — same spirit, my code.

> Status: working MVP — model + skills + a bounded tool-calling agent loop +
> policy-driven local model routing + local private memory + a Siri-style voice
> UI (web + native macOS app) + CLI.
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
python -m cognitive_twin --model llama3.2 "..."   # pin one model (routing off)
python -m cognitive_twin --route-explain "..."    # show which model the policy picked
python -m cognitive_twin voice --web              # 🎙 Siri-style voice UI (browser)
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
  agent/router.py        policy-driven model routing (local-first, by rule)
  agent/loop.py          route → persona + tools → model → run tool → feed back → repeat
  cli.py                 one-shot + REPL entrypoint
```

The loop is **bounded** (a step limit) and skills never crash it (errors are fed
back to the model to recover) — deterministic guardrails over an autonomous loop.
Persona comes from `system_dna.md`.

## Model routing (local-first, by policy)

Rather than send every request to one model — or to the cloud — the agent picks a
**local model per request** from a policy file. This is the "right model for the
job, on device" idea behind local-first agent research like
[OpenJarvis](https://github.com/open-jarvis/OpenJarvis); here it's data-driven and
inspectable.

`policies/model-routing.policy.json` defines the models and the rules:

```jsonc
"routingRules": [
  { "id": "rule_low_power", "when": { "deviceState": ["battery_saver"] }, "useModel": "fastFallback" },
  { "id": "rule_deep_path", "when": { "taskComplexity": ["high"], "riskLevel": ["medium","high"] }, "useModel": "deepPlanner" },
  { "id": "rule_fast_path", "when": { "taskComplexity": ["low","medium"], "riskLevel": ["low"] }, "useModel": "primary" }
]
```

A small, transparent heuristic (`agent/router.py`) classifies each prompt into
`taskComplexity` + `riskLevel` (length + a few keyword cues — no extra model call),
then the first matching rule wins. Signal device state with
`CTWIN_DEVICE_STATE=battery_saver` to exercise the low-power rule. `--route-explain`
prints the decision; `--model`/`--no-route` pins one model. If the routed model
isn't pulled, the agent stays local and falls back to an installed one.

The heuristic is deliberately simple and honest — a starting signal, not a learned
policy. Swapping in a learned classifier later is a drop-in. `guardrails.allowCloudFallback`
is `false`: routing never leaves the machine.

## Twin Voice — a local-first, Siri-style front end

Talk to the twin. Speak a question, it answers out loud — built in the spirit of
[Unhosted](https://github.com/unhosted-ai): the work stays on your machine.

```bash
python -m cognitive_twin voice            # native macOS menubar (needs rumps)
python -m cognitive_twin voice --web      # browser UI, zero extra deps
```

The browser UI uses [kopiro/siriwave](https://github.com/kopiro/siriwave) for the
reactive Siri wave (bundled locally — no CDN). The wave tracks state: resting →
**listening** (big, fast) → **thinking** (quiet shimmer) → **speaking** (lively).

How the voice loop stays local:

| Piece | How | Local? |
|---|---|---|
| Text-to-speech | macOS `say` | ✅ built in, offline |
| Speech-to-text (web UI) | browser Web Speech API | ⚠️ browser-dependent (some use a cloud service) |
| Speech-to-text (CLI/menubar) | local Whisper (`faster-whisper`) | ✅ on-device, optional install |
| Reasoning | the agent loop + Ollama | ✅ on-device |
| Server | stdlib HTTP on `127.0.0.1` only | ✅ never exposed off the machine |

### What works today (honest status)

| Capability | Status | Notes |
|---|---|---|
| `say` talk-back | **shipped** | offline macOS voice; `/api/speak` |
| Siri web UI (siriwave) | **shipped** | served at `127.0.0.1:7878`, verified |
| Browser speech → agent → spoken reply | **shipped** | full loop via the web UI |
| Live model routing in the voice path | **shipped** | reuses the tested router + fallback |
| Local Whisper STT | **optional** | `pip install -r requirements-voice.txt` |
| Native menubar launcher | **optional** | needs `rumps`; thin wrapper over the server |

No model installed for the policy? The voice path falls back to a tool-capable
installed model (same logic as the CLI) so it still answers — locally.

## Memory — local, private, secure

The twin learns your patterns and stores them **on your machine only** — a single
file (`~/.cognitive-twin/memory.jsonl`, override with `CTWIN_MEMORY_DIR`) written
owner-only (chmod `0600`). There is no network code in the memory module; nothing
is profiled off-device.

```bash
python -m cognitive_twin memory          # what's stored (counts + top topics)
python -m cognitive_twin memory clear    # wipe it — you're in control
```

From that log the agent derives a short, private summary of your recurring
interests and folds it into its system prompt, so it reasons more **like you** —
the actual point of a "twin." A new skill uses the same signal:

```bash
python -m cognitive_twin "give me thoughts of the day"
```

`thoughts_of_the_day` connects today's tasks with your recurring interests and
writes a short reflection in your own voice — all from local context.

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
