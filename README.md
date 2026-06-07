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

## Status

Phase 1 implemented: canonical system prompt plus runnable local orchestrator.
