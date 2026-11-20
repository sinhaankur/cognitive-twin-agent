<p align="center">
  <img src="docs/vera-hero.png" alt="Vera — a private, on-device AI twin" width="820" />
</p>

<h1 align="center">Vera</h1>

<p align="center"><em>A private, on-device twin of someone you love — in their voice, on your machine, never the cloud.</em></p>

<p align="center">
  <img alt="local-first" src="https://img.shields.io/badge/local--first-yes-2ea043" />
  <img alt="cloud" src="https://img.shields.io/badge/cloud%20sync-zero-2ea043" />
  <img alt="llm" src="https://img.shields.io/badge/LLM-on--device%20(Ollama)-4d6ef0" />
  <img alt="platforms" src="https://img.shields.io/badge/macOS%20·%20iOS%20·%20CLI-informational" />
  <img alt="license" src="https://img.shields.io/badge/license-AGPL--3.0-blue" />
</p>

---

**Vera** (Latin *verus* — **true**) is a private, on-device twin of someone you love.
You shape a persona of *your* person — their character, their voice, their stories —
and it carries their warmth forward. A floating orb on your screen: tap it, and chat —
type or talk, and it answers warmly, in their voice.

**Everything stays on your machine.** A twin of a loved one is the one thing you can
*never* hand to a cloud. So Vera doesn't: it thinks on a **local LLM**, keeps its memory
**sealed on your device**, and generates the **voice locally**. Nothing leaves unless *you*
allow it.

## Install

| Platform | How |
| --- | --- |
| **macOS** | Download `Vera.dmg` from [**Releases**](https://github.com/sinhaankur/cognitive-twin-agent/releases/latest), drag into Applications, right-click → Open. |
| **Run from source** | `./run.sh` — sets up, starts her brain, opens the UI. |
| **Linux / Windows / server** | `pipx install cognitive-twin-agent` then `vera-app` — or `docker compose up -d`. |

She thinks on a local model via [Ollama](https://ollama.com): `ollama pull qwen2.5:3b` (or her own `vera-tuned`).

## Use her

- **Make her yours** — `python -m cognitive_twin setup` (name, persona, voice — all on-device).
- **Talk** — tap the orb, type or speak. She remembers your days, feels the moment, and has a
  voice for every emotion.
- **Your people can meet her** — recognised guests get a warm chat; your private world stays yours.
- **Drop a PDF** into the chat and she'll read and discuss it.

## Private by design

- Thinks on a **local LLM**, sealed memory (ChaCha20), secrets in the Keychain — **zero cloud by default**.
- A **kill switch**, reach control (this Mac / your devices), and a built-in security audit.
- Opt-in senses (camera, mic, Photos, Calendar, Mail, Location) — off until you turn them on, nothing uploaded.

## More

- **[Roadmap](ROADMAP.md)** — what's built, what's missing, what's next.
- **[Full docs](docs/README-full.md)** — the complete guide (model routing, memory, automations, skills, and more).
- **[Privacy](PRIVACY.md)** · **[Security](SECURITY.md)**

---

<p align="center"><em>The privacy isn't a feature here — it's the only thing that makes a twin of someone you love possible at all.</em></p>
