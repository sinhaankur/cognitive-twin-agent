# Human-in-the-Loop Training

## Phase 1: Review-Before-Commit

- Agent drafts code/architecture/UI flow.
- Human reviews before merge or execution.

## Phase 2: Rule Learning

When output misses expectations:

- Update behavior spec or system prompt.
- Update critique ledger rules.
- Avoid one-off patching without upstream rule updates.

## Graduation Criteria

Promote autonomy only after consistent pass rates on:

- Tone gate
- Architecture gate
- UX gate
- Risk gate
