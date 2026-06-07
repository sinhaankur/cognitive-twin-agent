# Self-Correction Ledger

Before finalizing any output or commit, verify:

## Tone Gate
- Is this too corporate/verbose?
- Is the output concise and technically precise?

## Architecture Gate
- Did we introduce avoidable cloud coupling?
- Are local-first alternatives evaluated?

## UX Gate
- Is hierarchy obvious?
- Are failure states and reversibility visible?

## Risk Gate
- Any destructive action without confirmation?
- Any security/privacy leakage risk?

If any gate fails: redraft and re-evaluate.
