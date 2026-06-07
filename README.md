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
- `src/consent_manager.py`: Per-connector consent registry
- `src/connectors.py`: Real connector adapters (Google Calendar, Notion, Todoist)
- `src/calibration.py`: Threshold calibration from recorded sample sessions
- `src/sentiment_classifier.py`: Local transformer-based sentiment classifier
- `src/benchmark_sentiment.py`: Sentiment benchmark runner
- `src/menubar_controller.py`: Lightweight macOS menu-bar controller
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
- state encrypted at rest (Fernet)
- encryption key stored in OS keychain
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

Grant connector consent:

```bash
python src/assistant_daemon.py consent --connector google_calendar --allow
python src/assistant_daemon.py consent --connector notion --allow
python src/assistant_daemon.py consent --connector todoist --allow
```

Revoke connector consent:

```bash
python src/assistant_daemon.py consent --connector notion --revoke
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
	--connector-refresh-seconds 300 \
	--connector-refresh-jitter-ratio 0.2 \
	--iterations 12 \
	--interval 300
```

The daemon writes latest output to `memory/runtime/latest_assistant_output.md`.
Connector refresh health is written to `memory/runtime/connector_health.json`.

### Real Connector Credentials

Set connector credentials in `.env` (used only when consent is granted):
- `GOOGLE_CALENDAR_API_KEY` (optional fallback)
- `GOOGLE_CALENDAR_ID`
- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_OAUTH_REDIRECT_URI`
- `NOTION_API_TOKEN`
- `NOTION_DATABASE_ID`
- `TODOIST_API_TOKEN`

### Private Google OAuth Flow (Refresh + Keychain Storage)

Begin OAuth flow and wait for loopback callback automatically:

```bash
python src/assistant_daemon.py google-oauth-begin --auto-callback
```

OAuth UX options:

```bash
python src/assistant_daemon.py google-oauth-begin \
	--auto-callback \
	--timeout-seconds 180 \
	--max-attempts 3
```

Notes:
- Browser opens automatically by default.
- Use `--no-open-browser` for manual handling.
- Callback timeout triggers retry until attempts are exhausted.

If you want manual code exchange instead:

```bash
python src/assistant_daemon.py google-oauth-begin
python src/assistant_daemon.py google-oauth-exchange --code "AUTH_CODE" --state "STATE"
```

Check token status:

```bash
python src/assistant_daemon.py google-oauth-status
```

Tokens are stored in OS keychain and refreshed locally when nearing expiry.

### Connector Delta Sync + Backoff

- Notion sync uses cached delta merge keyed by page id + `last_edited_time`.
- Todoist sync uses sync-token incremental updates.
- Both connectors use exponential backoff with Retry-After handling on rate limits.

Generated connector cache files live under:
- `memory/connectors/cache/`

### Task Mapping Inputs

Populate connector files to map daily work:
- `memory/connectors/calendar.json`
- `memory/connectors/tasks.json`

Expected format for both files is JSON array of objects.

### macOS Auto-Start (LaunchAgent)

1. Copy `deployment/com.cognitive.twin.agent.plist.example`.
2. Replace workspace path and token placeholders.
3. Load with `launchctl` under your user context.

## Transcription Caching and Device Auto-Selection

Whisper model downloads are cached under `memory/models` by default and reused across runs.

Device behavior:
- `--transcription-device auto` tries CUDA first and falls back to CPU.
- Override with `--transcription-device cpu` or `--transcription-device cuda`.

Example:

```bash
python src/multimodal_orchestrator.py \
	--task "Summarize my state" \
	--enable-audio \
	--enable-transcription \
	--transcription-device auto \
	--model-cache-dir memory/models \
	--consent "I AGREE"
```

## Calibration from Recorded Sessions

Record samples while running multimodal mode:

```bash
python src/multimodal_orchestrator.py \
	--task "Calibration pass" \
	--enable-camera \
	--enable-audio \
	--enable-transcription \
	--record-calibration-label focused \
	--consent "I AGREE" \
	--iterations 20 \
	--interval 2
```

Compute calibrated thresholds:

```bash
python src/multimodal_orchestrator.py \
	--task "Rebuild thresholds" \
	--compute-calibration \
	--iterations 1
```

Generated profile path: `memory/calibration/threshold_profile.json`.

## Sentiment Classifier and Benchmark

The runtime uses a local transformer sentiment classifier instead of the old keyword heuristic.

Benchmark command:

```bash
python3 src/benchmark_sentiment.py \
	--samples benchmarks/sentiment_samples.jsonl \
	--report benchmarks/latest_sentiment_report.md
```

## Menu-Bar Controller (macOS)

Start the menu-bar app:

```bash
python3 src/menubar_controller.py
```

Environment requirement:
- set `AGENT_DAEMON_TOKEN` in `.env` to enable Start Daemon and Quick Voice Trigger.

### Signed Local IPC

The menu-bar app now talks to daemon via signed local IPC (UNIX socket) instead of direct shell control for status/stop/trigger commands.

Menu-bar status pane:
- Use "Connector Health" to view refresh status, last refresh time, item counts, failures, and next refresh ETA.

Security details:
- per-machine shared IPC secret stored in OS keychain
- HMAC-signed command envelopes
- local socket endpoint: `memory/runtime/daemon.sock`
- nonce replay protection persisted across restarts

## Status

Phase 1 implemented: canonical system prompt plus runnable local orchestrator.
