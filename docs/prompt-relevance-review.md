# Prompt Relevance Review

The proposed digital-twin prompt is relevant and aligns with the project direction.

## What is strong
- Clear role and identity definition
- Explicit local-first bias
- Communication style constraints that avoid generic assistant tone
- Built-in self-critique loop

## What needed tightening
- Add explicit safety and reversibility checks
- Clarify cloud dependency policy as constraints-driven, not absolute
- Add an output contract for consistent structure on complex tasks
- Keep tool execution bounded to avoid overreach in autonomous mode

## Resulting recommendation
Use `system_dna.md` as the canonical operating prompt and keep `prompts/system.prompt.md` as a shorter fallback version. For production behavior consistency, bind prompt policy to executable checks in the critique ledger.
