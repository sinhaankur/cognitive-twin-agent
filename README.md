# Cognitive Twin

A **personal AI twin** that runs on your own machine — a digital version of *you*.
It learns who you are (a persona you create), how you actually behave (private,
on-device memory), reasons with a local model, and calls **skills** to do real
things: greet you with the weather, research the web, see your screen, summarize
your day. Local-first by default; nothing leaves the machine unless you allow it.

Inspired by [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) ("Personal AI,
on personal devices"). This is an original implementation — same spirit, my code.

> Status: working MVP — persona + private memory + a bounded tool-calling agent
> loop + policy-driven local model routing + Apple Intelligence backend + web
> research + a Siri-style voice UI (native macOS app + web) + CLI.
> Open source (MIT). The `src/` tree holds earlier scaffolding (OAuth connectors,
> IPC, multimodal) kept as future layers; the runnable agent is the
> `cognitive_twin/` package; the native app is in `macos/TwinVoice/`.

## What it can do

- **Be you** — a persona (likes, dislikes, values, style) you create, so it
  reasons and speaks as you, not a generic assistant. → [Persona](#persona)
- **Remember you** — private, on-device memory of how you actually behave; folds
  into how it answers. Clearable anytime. → [Memory](#memory--local-private-secure)
- **Pick the right brain** — routes each request to the best local model by task;
  can use **Apple Intelligence** on-device, or Ollama models you choose.
- **Research the web** — search + read pages, the way Claude does (opt-in).
- **Greet you** — "good morning" with today's date and live weather.
- **See your screen + act** — read what's on screen, open apps/URLs/Shortcuts,
  all permissioned and confirmed (opt-in). → [Screen control](#screen-control--opt-in-permissioned-safe)
- **Talk** — a native macOS Siri-style app: speak to it, it speaks back.
- **Reflect** — "thoughts of the day" connecting your tasks with your interests.

## Why

Local models already handle a large share of everyday queries. The gap is the
*software around them*: a persona, a skill system, and a reliable loop that turns
"do X" into real actions — locally, privately, on hardware you own.

## Quick start

```bash
# 1. install Ollama (https://ollama.com) and pull a tool-capable model
ollama pull qwen2.5:3b        # or llama3.2, etc.

# 2. make it yours (recommended) — describe who your twin is
python -m cognitive_twin persona setup

# 3. run the agent (no Python deps needed for the core)
python -m cognitive_twin "what's the date?"
python -m cognitive_twin "good morning"           # greeting + weather (needs CTWIN_WEB=1)
python -m cognitive_twin "summarize my day"       # daily_digest skill
python -m cognitive_twin                          # interactive REPL
python -m cognitive_twin --skills                 # list available skills
python -m cognitive_twin --route-explain "..."    # show which model the policy picked
python -m cognitive_twin voice --web              # 🎙 Siri-style voice UI (browser)
```

Want the native Mac app instead of the browser? Build it once:

```bash
cd macos/TwinVoice && ./build-app.sh && open "Twin Voice.app"
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

## Persona

The thing that makes this *your* twin: a small, local, editable profile — name,
about, traits, **likes**, **dislikes**, values, communication style, expertise.

```bash
python -m cognitive_twin persona setup    # guided: describe who your twin is
python -m cognitive_twin persona          # show it + how the twin "sees" you
python -m cognitive_twin persona clear
```

Stored owner-only at `~/.cognitive-twin/persona.json` and compiled into a
"WHO YOU ARE" block in the system prompt, combined with `system_dna.md` and your
behavioral memory. The result: the twin reasons, decides, and speaks as you — e.g.
with a persona that likes Rust and values privacy, "what stack should I use?"
yields a local-first Rust answer, in your voice.

## Web research (opt-in)

Local-first by default, but the twin can reach the internet when you allow it
(`CTWIN_WEB=1`; the macOS app enables it for its agent automatically):

- `web_search` — DuckDuckGo (no API key) → top results with title, URL, snippet.
- `fetch_url` — fetch a page and strip it to readable text.
- `greeting` — "good morning" + date + live local weather (open-meteo, no key).

Search-then-read, the way Claude does it — every call gated behind the opt-in.

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

## Screen control — opt-in, permissioned, safe

The twin can *see* your screen and take a few *safe* actions — but only if you
turn it on. It deliberately does **not** do blind mouse/keyboard control.

```bash
python -m cognitive_twin control                       # show state (OFF by default)
CTWIN_CONTROL=1 python -m cognitive_twin "what app am I in?"   # enable for a run
```

Safety model:

- **Off by default.** Nothing works unless you set `CTWIN_CONTROL=1` (or enable it
  at runtime). 
- **Read actions** — `see_screen`, `read_screen` — never change anything (they use
  macOS Accessibility; grant permission the first time in System Settings →
  Privacy & Security → Accessibility).
- **Safe actions** — `open_app`, `open_url`, `run_shortcut` — are **confirmed per
  action**. In the terminal you get a `y/N` prompt; deny and nothing runs. App
  names / URLs / shortcut names are validated and passed as arguments to specific
  binaries — never interpolated into a shell.
- In the voice app, mutating actions are auto-denied unless you opt into
  `CTWIN_CONTROL_AUTOCONFIRM=1` (there's no dialog yet); read actions work when
  control is enabled.

This is the "assistant that can act," kept honest: local, scoped, and reversible.

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
