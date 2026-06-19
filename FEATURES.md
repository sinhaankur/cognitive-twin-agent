# Features — Cognitive Twin (Anita)

A personal AI twin that runs **on your own machine**. It learns who you are,
remembers how you think, and helps you through your day — **private and local by
default**. Nothing leaves your device unless you explicitly turn it on.

> Part of the [UnhostedAI](https://unhosted-ai.github.io/) family — local-first
> AI on hardware you own.

---

## 🔒 Private & local — the core promise

- **Runs on your machine.** Reasoning happens via a local model (Ollama, an
  OpenAI-compatible server like LM Studio, or **Apple Intelligence** on-device).
- **Your data stays yours.** Persona, memory, and her evolving personality live in
  `~/.cognitive-twin/`, written **owner-only (chmod 0600)**. No accounts, no cloud.
- **No telemetry.** There is no analytics or phone-home anywhere in the agent.
- **Off by default for anything outside the machine.** Internet access and screen
  control are explicit opt-ins (`CTWIN_WEB=1`, `CTWIN_CONTROL=1`).
- **You're in control.** Inspect or wipe everything: `ctwin memory clear`,
  `ctwin persona clear`, and a Clear button in the app.

## 🧬 She becomes *you* (personalization)

- **Persona you create** — name, likes, dislikes, values, style — so she reasons
  and speaks as you would, not a generic assistant.
- **Private memory** — learns your recurring interests and day-to-day patterns
  from your conversations, on-device.
- **A personality that grows** — over time she develops her own familiarity and
  tone from how you actually talk, becoming more herself the more you share.

## 🗣️ Natural to talk to

- **Voice in, voice out** — speak to her; she answers in a warm, human voice (not
  robotic), with tap-to-interrupt.
- **Or just type** — a clean chat panel, like a modern assistant.
- **Always there** — a small floating orb on screen (no Dock clutter); click for
  the chat. Launches at login, stays running, restarts itself if needed.

## 🧠 Genuinely helpful

- **Greets you** — "good morning" with the date and live local weather.
- **Thought of the day** — connects today's tasks with your interests.
- **Thinks while you're away** — keeps mulling your ideas and projects, and brings
  thoughts back when you return.
- **Researches the web** — searches and reads pages (opt-in), the way a capable
  assistant does.
- **Acts on your behalf** — with permission, can see your screen and open apps,
  URLs, and Shortcuts (every action confirmed; no blind control).

## 🧩 Your model, your choice

- Pick any local model (Ollama / LM Studio / OpenAI-compatible), switch live.
- Use **Apple Intelligence** on-device where available.
- Routes the right local model per task (quick for simple, deeper for complex).

## 🌍 Runs everywhere (open source)

A shared **Rust core** compiles to **macOS, iOS, iPadOS, Windows, Linux, Android,
and the web** — one brain, every device. MIT-licensed.

---

### Status (honest)

Working today: the macOS app (floating Anita), the local agent + skills, persona +
memory + evolving personality, web research, screen control, model routing,
Apple Intelligence. The Rust core builds for all six platforms; native shells
beyond macOS (iOS/Android/Windows/Linux) are in progress. See the per-area docs
in [README](./README.md).
