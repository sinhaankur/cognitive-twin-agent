# Vera as your local-AI hub — master plan (north star)

Ankur's vision, in his words: **"a single app that understands everything and stays
connected — like Gemini does it."** Vera = **your own Gemini, but LOCAL and PRIVATE.**

One app. You open it, you talk, it just works — across your projects, your code,
your life. Companion AND coding partner in ONE surface.

## THE CORE PRINCIPLE: context is the product
Ankur: **"contextual things matter the most."** This is the thesis in one line.
The model's raw intelligence is a commodity (qwen3-coder, any model, is "smart").
What's UNIQUE and valuable is YOUR CONTEXT — your code, your email, your people,
your day, your history — held privately and woven into every answer. That's what
makes it "yours, not random GPT." So the real engineering goal is NOT "best model";
it is **"hold as much of the user's real context as possible, safely, and bring the
RIGHT slice of it to each moment."** Every "organ" below is a context source; the
whole app is a context engine with a chat surface on top.

## THE DESIGN PRINCIPLE (this is the whole point)
**Hide ALL the complexity. The user never sees the machinery.**
- No LM Studio ports, no `CTWIN_*` env vars, no launchd agents, no "pick a model".
  ("LM Studio is too complex" — exactly. Vera manages the backend invisibly.)
- It picks the right model itself (qwen3-coder for code, vera-tuned for companion),
  starts/stops the server itself, stays connected itself.
- Like Gemini: ONE box, everything behind it invisible. That simplicity IS the
  product. If the user has to think about infrastructure, we failed.

What it IS underneath (invisible to the user):
- **Companion mode** — the cognitive twin of a loved one (the existing Vera).
- **Coding mode** — a local coding partner (qwen3-coder + RAG over his repos).
- Backend: **Ollama OR LM Studio**, auto-managed. Ankur likes LM Studio's models
  but not its complexity → Vera is the friendly face; LM Studio/Ollama hide behind.

## IT UNDERSTANDS *YOU* — "not just random GPT"
The thesis: a generic chatbot (Gemini/GPT) is smart but doesn't know YOU, and isn't
yours. This does — and it's PRIVATE + ON-DEVICE. It knows your code, projects,
email, calendar, the people in your life, how you work — and uses that to actually
help. That personal grounding is the product; the chat box is just the surface.

**The astonishing part: Vera ALREADY has the organs for this** (they exist, just
not unified into one "it knows everything" experience):

| "Understands everything" | Vera module (already built) |
|---|---|
| Your code / projects | codepartner RAG (rag-engine, built today) |
| Your email | `email_triage.py` (IMAP, local) |
| Your calendar | `calendar.py` |
| Your contacts | `contacts.py` |
| **Knows you personally** | `life_story.py`, `memory.py`, `life_memory.py`, `keepsake.py` |
| Your activity / what you're doing | `presence.py`, `activity.py`, `app_context.py` |
| Private + on-device | `security.py` egress kernel (local-only, consent-gated) |

So the build is NOT "invent a personal AI" — it's **unify the organs Vera already
has into ONE app that feels like a private Gemini that's truly yours.**

## ⚠️ The consent line (Ankur's own boundary — honor it)
Ankur previously DECLINED letting Vera read live email/photos ([[project_brain_engine_vera_integration]]).
"Knows my email" is powerful but personal. Rule for this vision:
- Every personal source (email/calendar/contacts) is **opt-in, per-source, and
  local-only** — the user explicitly turns each on; nothing is read without consent;
  nothing ever leaves the Mac (the egress kernel enforces this).
- The product can be "it understands everything" AND "I control exactly what it
  sees." Those aren't in tension — that control is WHY local beats Gemini.

> DISCIPLINE (the session's hard-won lesson): this is weeks, not a sitting. Finish
> ONE rung to quality before the next. The brain is LIVE — never risk it on a blind
> refactor. Plan → verify alongside → cut over only when proven.

## The architecture

```
                    ┌──────────────── Vera.app ────────────────┐
                    │  one window, two modes (toggle)           │
                    │                                           │
                    │   💛 Companion            🛠 Coding        │
                    │   (the twin: persona,     (qwen3-coder +  │
                    │    life story, memory,     RAG over your  │
                    │    voice)                  repos)         │
                    └───────────────┬───────────────────────────┘
                                    │ both talk to
                    ┌───────────────▼───────────────┐
                    │  ONE vera service (brain)       │  ← unified (see
                    │   • chat + tools + memory       │    UNIFY-SERVICES-PLAN.md)
                    │   • RAG retrieval over repos    │
                    │   • diagnostics (internal timer)│
                    └───────────────┬─────────────────┘
                                    │ model backend (either/or)
                    ┌───────────────▼───────────────┐
                    │  Ollama  OR  LM Studio          │  ← MultiBackend already
                    │  (qwen3-coder, vera-tuned, …)   │    routes to either
                    └─────────────────────────────────┘
```

## What already exists (most of it!)
- ✅ Companion mode = current Vera (brain, persona, life_story, memory, voice).
- ✅ Model backend abstraction = `cognitive_twin/llm/providers.py` MultiBackend
  (Ollama + OpenAI-compatible/LM Studio + Claude). "Use LM Studio too" is a config
  flag (`CTWIN_USE_LMSTUDIO=1` / `CTWIN_OPENAI_BASE`), already built.
- ✅ Coding brain = `qwen3-coder:30b` (in Ollama) — research-confirmed best for the
  32GB M1 Max.
- ✅ RAG over repos = `~/Documents/rag-engine` + `codepartner.sh` (10,625 chunks
  indexed, cites real files, works). This is the coding-mode knowledge layer.
- ✅ The app shell = `cognitive_twin/desktop.py` (starts brain + opens web UI).
- 📋 Service unification = docs/UNIFY-SERVICES-PLAN.md (fold 3 agents into one).

## What's new to build (the gaps)
1. **A mode concept in the app** — Companion ⇄ Coding toggle in the Vera web UI.
2. **Coding mode wiring** — route coding-mode chats to `qwen3-coder` with RAG
   context pulled from the repo index (reuse rag-engine's retrieval; Vera already
   has its own RAG for the twin — generalise it to also serve a "code corpus").
3. **One service does both** — the unified vera service exposes both a companion
   endpoint and a code endpoint (or one endpoint with a `mode` param).
4. **Clients** — the same hub reachable from VS Code (Continue.dev → the code
   endpoint) and the phone, over Tailscale. Vera already does cross-device.

## Phased roadmap (ORDER MATTERS — one rung at a time)
**P0 — prove the parts separately (DONE).** Companion works; coding partner works.
**P1 — unify Vera's services** (UNIFY-SERVICES-PLAN.md): 3 agents → 1 clean service.
   No new features; just clean flow. Verify the brain never drops.
**P2 — add Coding mode to the Vera app.** A mode toggle; coding chats hit
   qwen3-coder + the repo RAG index. Keep companion untouched.
**P3 — one backend switch.** Surface Ollama vs LM Studio choice in Vera's unified
   Settings (the toggle already exists in config; expose it in the UI).
**P4 — clients.** VS Code (Continue.dev) + phone point at the hub's code endpoint.
**P5 — keep it fresh.** The repo index auto-reindexes on the side (codepartner's
   launchd agent) so coding mode always knows current code.

## Guardrails
- The companion (the emotional core — his late mother) is SACRED. Coding mode is
  additive; it must never alter persona/voice/memory behaviour.
- One service, but failures isolated: a coding-mode error must never take the
  companion down, and vice-versa.
- Local-first: nothing leaves the Mac. LM Studio/Ollama are both on-device.

## NOT now (resist)
No new models, no HF Jobs/ZeroGPU, no multimodal, no new games. Those are later
optimisations. The next concrete rung is **P1 (service unification)** — small,
safe, high-value — then P2.
