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
- `prompts/system.prompt.md`: Behavioral DNA prompt
- `docs/behavior-spec.md`: Decision style and constraints
- `docs/critique-ledger.md`: Pre-output quality gates
- `docs/hitl-training.md`: Human-in-the-loop calibration loop
- `examples/few-shot-index.md`: Placeholder for high-quality examples
- `memory/`: Local memory indexes and vector metadata (implementation-specific)

## Quick Start

1. Copy `agent_config.example.json` to `agent_config.json`
2. Point model endpoints to your local runners (Ollama/LM Studio)
3. Fill behavioral constraints in `docs/behavior-spec.md`
4. Add 5-10 curated examples in `examples/few-shot-index.md`
5. Run in review-before-commit mode first

## Status

Bootstrapped scaffold. Implementation runner intentionally left framework-agnostic.
