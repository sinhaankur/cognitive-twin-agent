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
- **Memory is encrypted at rest.** Conversation memory is sealed with
  ChaCha20-Poly1305 under a key held by *this device and account* (macOS
  Keychain) — copied off the machine, the files read as noise. Moving to a new
  device is deliberate: `ctwin vault export` writes one passphrase-encrypted
  bundle; `ctwin vault import` re-seals it under the new device's key (also in
  Settings → Privacy).
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

- **Voice in, voice out, the finished way** — your words appear live as you
  speak; pause and the turn submits itself (endpointing); **speak over her and
  she stops mid-word** (echo-safe barge-in — your interruption becomes your
  next turn). Soft synthesized chimes mark listening start and end; the orb
  punches on word onsets and sparkles with your sibilants.
- **Or just type** — a clean chat panel; the keyboard always wins over the mic.
- **She can see you — only if you ask** — a "See me" toggle. In the app it's
  Apple's Vision face landmarks, fully on-device: the preview shows only the
  landmark constellation (never video), auto-framed Face ID-style, and the
  dots *say what they read* — smile, knitted brow, blink rate, attention,
  nod, lean — measured geometry, never stored, never dressed up as
  "emotions", forgotten seconds after you turn it off. (In the browser it's
  the author's optical-flow engine, motion cues only, adapted from
  [the lab](https://sinhaankur.com/lab/optical-flow/).)
- **She can learn your life from Photos — only if you ask** — a "Read my
  Photos" switch reads album *names and dates only* (metadata, never pixels):
  birthdays, anniversaries, weddings, remembrances, and the unnamed days that
  fill with photos every year — stored as ordinary memories with their
  provenance, so she can ask "whose day is June 3rd?" instead of assuming.
- **Watch her think** — the Mind (`ctwin viz`): her memory as a living
  particle fluid (a real D2Q9 lattice-Boltzmann simulation, FluidX3D's method
  ported by hand), every real memory constellated around it, and a visible
  thought-flow when you ask her something. All real data, nothing staged.
- **Always there** — a small floating orb on screen (no Dock clutter); click for
  the chat. Launches at login, stays running, restarts itself if needed.

## 🧠 Genuinely helpful

- **Greets you** — "good morning" with the date and live local weather.
- **Thought of the day** — connects today's tasks with your interests.
- **Shadows your day** — catches tasks you mention in conversation ("remind me
  to…"), crosses them off when you say they're done, and carries the rest
  across days — no forms, no separate tracker.
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
and the web** — one brain, every device. AGPL-3.0-licensed.

---

### Status (honest)

Working today: the macOS app (floating Anita), the local agent + skills, persona +
memory + evolving personality, web research, screen control, model routing,
Apple Intelligence. The Rust core builds for all six platforms; native shells
beyond macOS (iOS/Android/Windows/Linux) are in progress. See the per-area docs
in [README](./README.md).
