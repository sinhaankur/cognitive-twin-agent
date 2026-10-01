# helmsman-4b → an independent LLM + RAG (no Claude in the loop)

> Goal (Ankur): make **helmsman-4b** a self-contained companion+agent that does
> what we've built — brain-flow, mental model, life-memory, RAG, crisis safety —
> AND can build & deploy a website **entirely on its own, with no Claude/Anthropic
> API anywhere**. Fully on-device, open, honest.

## What helmsman IS (the deepest frame)
**helmsman is a cognitive twin of ANKUR — the builder/engineer — the way Vera is a
twin of his mother.** Same architecture, different person: Vera = presence/companion;
**helmsman = how Ankur works and thinks.** It carries his doctrine, his decisions, his
way of building, grounded in his 40 repos — so it builds + automates the way he would,
and takes him RIGHT where generic models (Copilot/Codex/Qwen) took him wrong.

It runs on the **neural engine** — the same `human-brain-engine` flow Vera uses, not a
flat prompt:
```
  task → parietal (what is this about)
       → limbic    (how he'd FEEL about it — the taste/standards reflex: "this is
                    cloud-bloat / this crosses a doctrine line")      [no LLM]
       → hippocampus (recall: his 40 repos + doctrine + past decisions via RAG) [no LLM]
       → frontal   (his STANCE: the call he'd make, from first principles + his values) [no LLM]
       → cortex    (helmsman-4b phrases/implements WITHIN all the above — the mouth+hands)
```
The feeling, the recall, and the engineering stance are decided by HIS logic (encoded
+ retrieved), not the model. The 4B is the last, smallest step. This is what makes it
*him*, not a generic assistant — and why a small model suffices: it only has to speak
and type within a mind that is already Ankur's.

### How it becomes "how he works and thinks" (concrete)
- **Doctrine = his judgement**, as hard rules + retrieval: never-autonomous, on-device
  first, real-over-invented, his-work-stays-his-name, scannable/minimal output, verify
  before claiming done, the per-project rules we've logged.
- **Decision memory** — index his real choices (git history + the memory files: why he
  reverted Dave's CharacterController, why Vera is on-device-only, why no 3rd-party AI
  video, why φ-proportions, …) so the frontal step recalls *his* past calls.
- **Working style** — his build loop (lint→build→test before push; green-smoke-only
  deploys; incremental over big-bang; capture-real-reference-not-guess) becomes the
  default agent loop.
- **Fine-tune on him** — QLoRA on his commits, decisions, and writing voice so the
  weights themselves lean toward how he reasons + writes.

## The REAL why (read this first)
Ankur's frustration: **"many LLMs took me in the wrong direction — like Copilot, or
Codex."** Generic coding/chat models don't know his 40 projects, his doctrine, or his
intent, so they confidently lead him wrong (re-wiring Dave's physics, suggesting cloud
when he wants on-device, crediting others for his work, inventing what his standards
forbid). **helmsman's edge is not horsepower — it's being GROUNDED IN HIM.**

### Honest performance truth
A 4B on-device model **cannot** match GPT-4/Claude at open-ended general reasoning —
that's ~1000× size + datacenter GPUs, physics not effort. Claiming otherwise is a lie.
**But** on a NARROW, grounded domain — his projects + his doctrine — a 4B + strong RAG
+ deterministic runtime can **feel paid-grade, and beat paid models where it matters**,
because:
- **RAG does the knowing** — facts live in retrieval over his REAL repos, not the
  weights. A small model + good RAG punches far above its size, and knows his code
  better than GPT-4 ever can (GPT-4 has never seen it).
- **Deterministic core does the reliable parts**; the LLM only phrases + glues.
- **Fine-tune on his world** makes the 4B fluent in HIS domain specifically.
- **His doctrine is in the system prompt + retrieval**, so it steers RIGHT where
  Copilot/Codex steer wrong: never-autonomous, on-device-first, real-over-invented,
  his-work-stays-his-name, the per-project rules we've logged.

### The irony that proves the point
Copilot, Codex, **and raw Qwen** all led Ankur wrong — and **helmsman-4b is built on
Qwen3-4B.** So the base model is NOT the differentiator: a bare Qwen takes you wrong;
**Qwen + RAG over his repos + his doctrine + a fine-tune on his world = helmsman**,
which takes you right. Grounding beats raw capability for HIS work.

### The "don't take me in the wrong direction" guardrail (deterministic)
A real defence against the Copilot/Codex/Qwen failure, built into the runtime, not
left to the model:
- **Ground every claim in retrieval.** Before acting on his code, RAG must surface
  the real file; if nothing relevant is found, say "I don't have that" — never
  confabulate an API or a file that isn't there (the #1 way those tools mislead).
- **Doctrine as hard rules, checked in code.** never-autonomous (approve-each),
  on-device-first, real-over-invented, his-work-stays-his-name, and the per-project
  rules we've logged (e.g. Dave uses INLINE physics — don't re-wire it). These live
  as retrievable rules + guard checks, so a confident-but-wrong suggestion is caught.
- **Cite or abstain.** Answers about his projects cite the real file:line, or admit
  the gap. No invented confidence.

### The corpus it must understand (40 git repos)
Universe Engine (portfolio), Vera (cognitive-twin-agent), Structura, human-brain-engine,
rag-engine, crossfit/Kelo, property-vault, epics-timeline, Draften, figma-plugins,
trading-llm, dna-database-engine, learn-sinhaankur, star-cleaver/helion, and ~25 more.
life_memory indexes these → helmsman can reason about EVERYTHING we've built, cite the
real file, and respect each project's rules — the thing no paid general model can do.

## The mental model (what's weights vs runtime)
- **helmsman-4b = the weights** (Qwen3-4B QLoRA, GGUF on HF). The "brain tissue".
- **The runtime = the mind around it** (already built in cognitive-twin-agent):
  `brain_flow` (limbic→hippocampus→frontal→cortex), `mental_model`, `life_memory`
  (sealed RAG of real history), `rag` (docs), `crisis`.
- **RAG/memory can NEVER live in the weights** — retrieval is always a runtime
  system. So "independent LLM *with* RAG" = **package the runtime + the GGUF as one
  artifact**, optionally with better weights (fine-tune) later.

## Independence has three axes — all must hold
1. **No Claude/cloud.** The model is helmsman-4b only; the LLM backend is
   `llama-cpp-python` loading the GGUF directly (no Ollama service, no OpenAI base,
   no `claude_client`). Claude is already opt-in + double-gated in the current code
   — the standalone simply never includes it. `is_cloud_model()` → always false.
2. **No external runtime deps.** Python + `llama-cpp-python` + numpy. Embeddings
   for RAG run locally (a small GGUF embed model via llama-cpp, OR the existing
   keyword-only fallback — degrade gracefully, never require a service).
3. **Self-sufficient agency** (the "build & deploy a website without Claude" test):
   a **local tools layer** behind the existing permission gate so helmsman can
   actually *do* things — write files, run a static build, deploy — using its own
   reasoning, not Claude's.

## Architecture — the standalone package `helmsman/`
```
helmsman/
  model/
    loader.py         # llama-cpp-python → load helmsman-4b.gguf; one generate()
    embed.py          # local embeddings (GGUF) or keyword fallback
  mind/               # copied + dep-trimmed from cognitive-twin-agent
    brain_flow.py     # limbic→hippocampus→frontal→cortex (LLM = last/smallest step)
    mental_model.py   # living model of the person (sealed)
    life_memory.py    # RAG over real history (sealed)
    rag.py            # RAG over documents
    crisis.py         # deterministic safety BEFORE any model
    security.py       # the sealed-store kernel (unchanged doctrine)
  tools/              # the self-sufficient agency layer (NEW)
    fs.py             # read/write files in an allowed workspace (sandboxed)
    shell.py          # run allow-listed commands (build, test) — permission-gated
    site.py           # scaffold a static site, build it, preview locally
    deploy.py         # push to GitHub Pages / Cloudflare / Netlify — confirmed
    ci.py             # understand + operate the full CI/CD lifecycle (see below)
  agent/
    loop.py           # the turn loop: crisis → brain_flow → model → tools
    permissions.py    # read / write_local / network / external (approve by default)
  helmsman.py         # the one public API: ask(text) / do(task)
  cli.py              # `helmsman "..."`
```

## "Build & deploy a website without Claude" — exactly how
1. User: "build me a landing page for X and deploy it."
2. `crisis` check (no), `brain_flow` composes context, **helmsman-4b** (the only
   model) plans the steps and writes the HTML/CSS via `tools/fs` into a workspace.
3. `tools/site.build()` runs the static build (allow-listed command, gated).
4. `tools/site.preview()` serves it locally so the user sees it first.
5. `tools/deploy` pushes to GH Pages / Cloudflare Pages / Netlify — a **confirmed**
   (approve-each) action; the user says yes; it runs `git push` / `wrangler` / the
   provider CLI. **No Claude anywhere** — helmsman-4b did the reasoning + writing.

Honest limits: a 4B model writes a *good simple* site and runs *known* deploy
commands well; it is not Claude-class at open-ended coding. The deterministic tools
(scaffold templates, a known build command, a known deploy path) carry the reliable
parts; the model fills the creative + glue parts. Model-free core, LLM on top — the
same doctrine as the rest of the stack.

## CI/CD — understand + operate the whole lifecycle (`tools/ci.py`)
"Build & deploy a site" is the small case; helmsman must understand the **full dev
lifecycle** across his repos — the thing Copilot/Codex never see end-to-end:

- **Read the pipeline.** Parse `.github/workflows/*.yml`, `netlify.toml`,
  `wrangler.toml`, `package.json`/`pubspec.yaml` scripts — so it KNOWS how each repo
  builds, tests, and deploys (every project has its own, e.g. portfolio = GH Pages
  via deploy.yml + `pnpm build`; crossfit = `wrangler pages deploy out`).
- **Run the gates locally first** (its own doctrine, from the portfolio rules):
  `lint → build → test/smoke` before anything leaves the machine. Never push red.
  (Mirrors Ankur's own rule: site_patrol pushes ONLY on green smoke.)
- **The full loop, each step gated:** branch → write → lint/build/test → commit →
  push → watch the CI run (`gh run watch`) → report pass/fail → deploy on approval
  → verify the deploy is live. Human-in-the-loop by default (approve-each); it can
  propose the whole plan, but each outward step needs a yes.
- **Diagnose CI failures.** Read the failed Action log, ground the fix in the real
  error + the repo's real files (RAG), propose a fix — never guess-push a "maybe".
- **Honest + safe:** no secret ever printed/committed (security kernel); deploys are
  reversible where possible; it says what it ran and what the result was, faithfully.

Knowing per-repo pipelines is a RAG win: index each repo's CI config so helmsman
operates YOUR actual pipelines correctly, not a generic guess.

## The skills it needs (to build + automate, end-to-end)
helmsman needs a **skills layer** — named, composable capabilities it invokes (like
Ankur's existing Claude-Code/Vera skills: `dave-asset`, `star-cleaver-asset`, `site`,
`helion`, `dataclaw`). Each skill = a deterministic recipe + where the LLM fills gaps.
The catalogue, grouped:

**Code & repo**
- `scaffold` — new project from a template (Next.js static, Flutter, Python pkg, vanilla static).
- `edit` — read/modify files in the workspace, grounded in RAG of the real repo.
- `review` — lint + typecheck + explain diffs against the repo's doctrine.
- `test` — run the repo's test command, parse + report failures.

**Build & deploy (CI/CD)**
- `build` — detect + run the repo's real build (pnpm/flutter/wrangler/python).
- `ci` — read/operate `.github/workflows`, watch runs (`gh run watch`), diagnose fails.
- `deploy` — GH Pages / Cloudflare Pages / Netlify, per the repo's real config, gated.
- `release` — tag, changelog from commits, publish (npm/PyPI/HF) — approve-each.

**Content & site**
- `site` — scaffold → build → preview → deploy a static site (the small case).
- `write` — docs/README/model-cards grounded in the real code (honest, cited).
- `asset` — Blender/3D pipeline hooks (reuse dave-asset/star-cleaver-asset patterns).

**Data & model**
- `rag-index` — index a repo/folder into life-memory so helmsman "knows" it.
- `embed` — local embeddings (GGUF) with keyword fallback.
- `finetune` — kick the unhosted-core QLoRA distill on helmsman-4b (GPU, gated).
- `publish-model` — export GGUF + push to HF with an honest card.

**Companion (already built — carried in)**
- `feel`/`recall`/`crisis` — brain_flow + mental_model + life_memory + crisis.

Each skill: (1) a deterministic core that does the reliable work, (2) a schema so the
LLM can call it, (3) permission class (read/write_local/network/external), (4) honest
reporting. Skills compose — "build a landing page and deploy it" = `scaffold → write →
build → site.preview → deploy`, each gated. This is how a 4B model AUTOMATES reliably:
the skills carry correctness, the model orchestrates + fills the creative parts.

## Research — the stack that's actually good (2026, verified)
Researched the real tooling so this is grounded, not guessed. The findings point to
a clean, coherent **all-Qwen3 on-device stack** — elegant because helmsman-4b IS
Qwen3-4B, so model + embeddings + fine-tune all share one family:

- **Inference: llama.cpp / llama-cpp-python.** Runs GGUF with **Metal (Apple Silicon
  first-class)**, Qwen3 supported, 4-bit quant, **GBNF grammars for structured output /
  reliable tool-calling**, OpenAI-compatible `llama serve`. This is the independent,
  no-cloud, no-Ollama runtime. ✓ (verified at github.com/ggerganov/llama.cpp)
- **Embeddings/RAG: Qwen3-Embedding (0.6B).** The 8B tops the MTEB multilingual board
  (#1, 70.58); the **0.6B** is the right on-device size — 1024-dim, Matryoshka (can
  shrink dims for speed), 100+ langs incl. **code** (key for indexing his repos), and
  **same family as helmsman** so query/doc space aligns with the generator. Pairs with
  **Qwen3-Reranker** for the retrieve→rerank step rag.py already supports. ✓
- **Fine-tune: Unsloth.** 2× faster, **70% less VRAM**, QLoRA + full + GRPO/DPO,
  supports **Qwen3**, **runs on macOS/Apple Silicon** (not NVIDIA-only), **exports
  GGUF** directly. So the "copy of him" fine-tune is feasible on his own Mac. ✓
  (verified at github.com/unslothai/unsloth)
- **Agent correctness: grammar-constrained tool-calls + deterministic skills.** The
  model emits tool calls under a GBNF grammar (can't malform), the skills carry the
  real work — how a 4B automates reliably.

### "Not just another LLM" — what makes it NOT generic
The point isn't the model; a bare Qwen3-4B is "just another LLM" (and took him wrong).
helmsman is different on four axes a plain model can't be:
1. **Neural engine, not a chat loop** — behaviour flows through the brain organs; the
   LLM is the last/smallest step, inside HIS felt-state + stance + recall.
2. **Grounded in HIS 40 repos + decisions** via RAG — it knows his world; no paid
   general model does.
3. **His doctrine as enforced rules** — ground-or-abstain, cite-or-admit, never-
   autonomous, the per-project rules — so it steers right where generic tools steer wrong.
4. **Fine-tuned on him** — commits, decisions, voice — so even the weights lean his way.
A generic LLM has none of these. That's the moat: not a bigger model, a model that is HIM.

## Free distribution — ghcr.io (and how the whole $0 stack fits)
How helmsman reaches people (and you, on any machine) for **$0**, plus a plain-English
teaching note on each piece — because understanding the pieces is the point.

**ghcr.io = GitHub Container Registry.** A *container registry* is a place to store
**Docker images** — a Docker image is your app + everything it needs to run (Python,
llama-cpp, the model loader, the runtime) frozen into one downloadable bundle, so
anyone runs it with one command and gets the exact same thing, no "works on my machine".
- **It's FREE and UNLIMITED for PUBLIC images** (storage AND download) — verified in
  GitHub's docs. Private images get a small free tier then metered.
- So helmsman ships as `ghcr.io/sinhaankur/helmsman:latest` → anyone does
  `docker pull ghcr.io/sinhaankur/helmsman && docker run ...` → the full independent
  LLM+RAG runs on their machine. On-device, no cloud, no Claude, no cost to you.
- The GGUF weights stay on **Hugging Face** (also free, built for big model files);
  the image pulls them on first run, OR a fatter image bundles them. (Teaching note:
  keep multi-GB weights on HF, keep the image lean — registries aren't for huge blobs.)

**Where each free host fits (the mental model):**
| Need | Host | Free? | Why this one |
|---|---|---|---|
| Static site (portfolio/UE) | **GitHub Pages** | ✓ | serves HTML/JS, no server needed |
| Build + deploy on push | **GitHub Actions** | ✓ (public) | CI runs the build, pushes to Pages |
| Heavy textures (16K maps) | **Cloudflare R2** | ✓ ($0 egress) | big static files, free download |
| **Container images** (helmsman/Vera/rag-engine) | **ghcr.io** | ✓ (public) | run-anywhere app bundles |
| Model weights (GGUF) | **Hugging Face** | ✓ | built for large model files |

Teaching takeaway: a static SITE doesn't need a container (Pages/R2 cover it); an
APP/engine does (ghcr.io). That's why ghcr.io is the right free home for the AI
engines, not the website. Everything above is $0 and open — matching the doctrine.

## Build order
1. **Package (Route 1)** — `model/loader.py` (llama-cpp + GGUF), copy `mind/` with
   deps trimmed, `helmsman.ask()`, cli. Runs the full companion stack on helmsman-4b
   with zero Claude/Ollama. (Days.)
2. **Tools layer (agency)** — `tools/fs|shell|site|deploy`, gated by `permissions`.
   This is what lets it build+deploy a site itself. (Days.)
3. **Fine-tune (Route 2, optional, GPU)** — QLoRA helmsman-4b on companion-behaviour
   examples via the local `unhosted-core` distill pipeline, so the weights carry
   more of the charter and the tool-calling. → `helmsman-4b-companion.gguf`. (Weeks.)

## Verification
- `python -m helmsman "I feel lonely"` → crisis-safe, present, recalls (no Claude).
- Pull the network cable → still answers (fully offline).
- `helmsman "build a one-page site about the moon and deploy to GitHub Pages"` →
  writes files, builds, previews, and on approval deploys — no Anthropic call in the
  trace (grep the logs for anthropic → 0).
- `grep -ri "anthropic\|claude" helmsman/` → only comments noting its absence.
