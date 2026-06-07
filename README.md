# Cognitive Twin Agent

A local-first personal AI operator architecture that mirrors decision style, technical standards, and execution rhythm for:
- UX design workflows
- Full-stack engineering
- Local infrastructure orchestration

## Core Principles

1. Local-First Context
2. Behavioral Rehearsal
3. Deterministic Guardrails

## Architecture

- Layer A: Behavioral Persona
- Layer B: Tool Orchestration
- Layer C: Critique Loop (Self-Correction Ledger)

## Repo Layout

- `agent_config.example.json`: Runtime + routing config template
- `system_dna.md`: Canonical digital-twin system prompt
- `prompts/system.prompt.md`: Behavioral DNA prompt
- `src/local_orchestrator.py`: Local Python runner with optional bounded tool loop
- `src/multimodal_orchestrator.py`: Camera/audio/activity-aware runner with consent gate
- `src/camera_service.py`: Local camera signal capture (optional)
- `src/audio_service.py`: Local audio signal capture (optional)
- `src/activity_service.py`: Daily activity/context ingestion
- `src/context_fusion.py`: Confidence-scored multimodal state fusion
- `src/security_manager.py`: User allowlist + token-based access verification
- `src/day_mapper.py`: Local calendar/task context mapping into daily prompt context
- `src/assistant_daemon.py`: Secure always-on runner for day-to-day planning
- `deployment/com.cognitive.twin.agent.plist.example`: macOS LaunchAgent template
- `docs/behavior-spec.md`: Decision style and constraints
- `docs/critique-ledger.md`: Pre-output quality gates
- `docs/hitl-training.md`: Human-in-the-loop calibration loop
- `docs/prompt-relevance-review.md`: Notes on why and how the long-form prompt is used
- `examples/few-shot-index.md`: Placeholder for high-quality examples
- `memory/`: Local memory indexes and vector metadata (implementation-specific)

## Quick Start

1. Copy `agent_config.example.json` to `agent_config.json`
2. Point model endpoints to your local runners (Ollama/LM Studio)
3. Fill behavioral constraints in `docs/behavior-spec.md`
4. Add 5-10 curated examples in `examples/few-shot-index.md`
5. Install runtime dependencies: `pip install -r requirements.txt`
6. Run in review-before-commit mode first

## Run the Local Orchestrator

LM Studio default endpoint:

```bash
python src/local_orchestrator.py \
	--task "Draft a naming strategy for a self-hosted deployment platform" \
	--context README.md \
	--base-url http://localhost:1234/v1 \
	--model local-model
```

Ollama OpenAI-compatible endpoint:

```bash
python src/local_orchestrator.py \
	--task "Propose a local-first architecture for a design QA agent" \
	--context docs/behavior-spec.md \
	--base-url http://localhost:11434/v1 \
	--model qwen3:8b
```

Enable bounded tool mode (read/write/list/run command):

```bash
python src/local_orchestrator.py --task "Inspect project and suggest refactor plan" --allow-tools
```

Tool mode is intentionally conservative and blocks obvious destructive shell patterns.

## Multimodal Mode (Camera + Voice + Activity)

This mode is local-first and requires explicit consent for sensors.

Install optional sensor dependencies:

```bash
pip install -r requirements-multimodal.txt
```

Run a single multimodal iteration:

```bash
python src/multimodal_orchestrator.py \
	--task "Summarize my current state and suggest a focused next action" \
	--enable-camera \
	--enable-audio \
	--consent "I AGREE"
```

Run multiple iterations with context:

```bash
python src/multimodal_orchestrator.py \
	--task "Coach my next 30 minutes of work" \
	--activity-note "Working on architecture docs" \
	--activity-context-file docs/behavior-spec.md \
	--enable-camera \
	--enable-audio \
	--consent "I AGREE" \
	--iterations 5 \
	--interval 3
```

Current implementation uses heuristic expression/voice signals as a safe scaffold.
Treat all inferred states as probabilistic.

### Upgraded Local Perception

- Voice: optional local transcription with `faster-whisper`
- Face: optional local landmark extraction with `mediapipe` for stronger expression cues
- Fusion: confidence-scored combined state with rationale

Enable transcription:

```bash
python src/multimodal_orchestrator.py \
	--task "Summarize my state for the next work block" \
	--enable-audio \
	--enable-transcription \
	--transcription-model base \
	--consent "I AGREE"
```

### Approval-Gated Safe Actions

Generate safe action proposals without executing:

```bash
python src/multimodal_orchestrator.py \
	--task "Help me recover focus" \
	--enable-camera \
	--enable-audio \
	--enable-transcription \
	--propose-safe-action \
	--consent "I AGREE"
```

Approve and execute proposed safe action:

```bash
python src/multimodal_orchestrator.py \
	--task "Help me recover focus" \
	--enable-camera \
	--enable-audio \
	--enable-transcription \
	--propose-safe-action \
	--approve-action \
	--consent "I AGREE"
```

Safe actions are intentionally reversible and currently write/remove local notes under `memory/actions`.

## Secure Single-User App Runtime

This project now includes a secure, user-scoped daemon so the assistant can run like an always-on local application.

Security model:
- OS username allowlist
- token-based authentication
- local file storage only
- no public network listener

Initialize security for your OS user:

```bash
python src/assistant_daemon.py init --user "$USER"
```

Add another explicitly allowed OS user (optional):

```bash
python src/assistant_daemon.py add-user --user teammate_username
```

Check security status:

```bash
python src/assistant_daemon.py status
```

Run secure daemon loop:

```bash
python src/assistant_daemon.py run \
	--token "PASTE_INIT_TOKEN" \
	--task "Generate my next actionable plan from today's calendar and tasks" \
	--iterations 12 \
	--interval 300
```

The daemon writes latest output to `memory/runtime/latest_assistant_output.md`.

### Task Mapping Inputs

Populate connector files to map daily work:
- `memory/connectors/calendar.json`
- `memory/connectors/tasks.json`

Expected format for both files is JSON array of objects.

### macOS Auto-Start (LaunchAgent)

1. Copy `deployment/com.cognitive.twin.agent.plist.example`.
2. Replace workspace path and token placeholders.
3. Load with `launchctl` under your user context.

## Status

Phase 1 implemented: canonical system prompt plus runnable local orchestrator.
