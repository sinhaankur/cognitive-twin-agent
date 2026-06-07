# Cognitive Twin Agent - Customer Journey Map

This document maps how an individual customer purchases, activates, and uses the local assistant safely.

## Journey Stages

1. Discover
- Prospect reads the public case-study page and understands scope:
  - individual-user assistant
  - private repository access
  - local-first architecture
  - consent-gated connectors

2. Qualify
- Prospect confirms fit:
  - one named user
  - macOS local runtime preference
  - willingness to run local models/connectors
  - privacy-first and explicit-consent workflow

3. Purchase
- Prospect contacts licensing email.
- Commercial terms and support scope are confirmed in writing.
- Payment is completed.

4. Provision
- User receives approved access:
  - private repository access and version scope
  - license note with individual-user entitlement
  - onboarding checklist and setup docs

5. Activate
- User completes local setup:
  - copy `agent_config.example.json` -> `agent_config.json`
  - configure model endpoints
  - initialize security (`assistant_daemon.py init --user`)
  - grant connector consent selectively

6. Calibrate
- User records baseline samples and computes threshold profile.
- Sentiment benchmark is run to establish initial quality metrics.
- Routing and memory policies are reviewed before continuous usage.

7. Daily Use
- Daemon runs authenticated loops.
- Menu-bar controls are used for status and quick actions.
- Calendar/task context drives day mapping and planning suggestions.

8. Govern
- Policy files govern model routing, memory retention, and trust/sync behavior.
- Connector health and runtime status are audited locally.
- Consent can be revoked per connector at any time.

9. Expand (Optional)
- Additional connectors or stricter policies are added.
- Deep planning routes are enabled for heavier reasoning tasks.
- Device trust policy is updated for secondary devices if licensed.

10. Renew or Exit
- Renewal includes support/update scope refresh.
- Exit path includes credential revocation and local data cleanup.

## Operating Flow (How It Works)

Input -> Security Gate -> Consent Gate -> Context Fusion -> Planner -> Human Approval -> Action/Output -> Local Audit

- Security Gate: verifies user allowlist + token.
- Consent Gate: includes only permitted connectors/sensors.
- Context Fusion: merges camera/audio/activity + task graph.
- Planner: routes to policy-defined model tier.
- Human Approval: required for any non-trivial side effects.
- Action/Output: writes to local runtime output only.
- Local Audit: logs health, sync status, and reversible action traces.

## Success Metrics

- Time-to-first-usable-plan after onboarding
- Day-plan relevance score (self-rated)
- Consent integrity (no unauthorized connector usage)
- Runtime reliability (healthy loop uptime)
- Calibration drift and benchmark trend over time

## Failure Modes and Guardrails

- Missing consent: fallback to local-only context.
- Connector outage: serve from cached snapshots + backoff retry.
- Policy mismatch: block startup in strict mode (recommended enhancement).
- Token/user mismatch: deny run immediately.

## Website Narrative Summary

Use this concise framing on the public website:

"Cognitive Twin Agent is a paid, individual-user local assistant runtime. It combines secure user-scoped access, consent-gated integrations, and policy-driven planning so your day-to-day work can be mapped into actionable plans without giving up local control."
