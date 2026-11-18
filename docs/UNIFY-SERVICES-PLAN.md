# Plan: unify Vera's background services (don't touch the running brain yet)

Ankur's question: *"shouldn't all of them be running from the Vera app? like one?"*
**Answer: yes.** Today Vera's lifecycle is fragmented across 3+ launchd agents that
install separately and overlap with what the app already does. This plans a clean,
app-centred model — to review BEFORE any change, because the brain is live + working
(PID running) and a blind refactor risks hours of breakage (see the stale-service
lesson in project memory).

## What exists today (the sprawl)

| Agent | Installed by | What it does | Problem |
|---|---|---|---|
| `com.sinhaankur.vera.brain` | `install-service.sh` | runs the brain server (:7878) **always**, even app-closed | **Overlaps the app** — `desktop.py` ALSO starts the brain when opened. Two owners. |
| `com.sinhaankur.vera.diagnostics` | `install-diagnostics.sh` | every 30 min pings `/api/diagnose` → trend log | A whole separate agent for something the brain could do itself on a timer. |
| `com.sinhaankur.ollama-host` | one-off plist | `launchctl setenv OLLAMA_HOST 100.x:11434` | Not really a "service" — a single env-set. Barely belongs here. |

The **Vera app (`cognitive_twin/desktop.py`) already** resolves the port and launches
the brain + web UI. So "the app starting Vera" is partly built — the launchd brain
agent duplicates/competes with it.

## The target model — ONE service, app-owned

```
   Vera.app (open it → Vera is up; quit → Vera stops)
        │  owns the lifecycle
        ▼
   ┌─────────────────────────────┐
   │  vera service (ONE)          │
   │   • brain + voice + web UI   │  (desktop.py already does this)
   │   • diagnostics on an INTERNAL timer (fold in — no separate agent)
   │   • sets OLLAMA_HOST at startup (fold in — no separate plist)
   └─────────────────────────────┘
```

Two valid shapes — pick one when we build:
- **A. App-owned (foreground-ish):** Vera runs only while the app is open. Simplest,
  matches "all from the Vera app". Diagnostics + ollama-host fold into the app's
  startup. No always-on launchd brain.
- **B. One background service + app as a window onto it:** keep ONE launchd
  `vera` service (so she's reachable headless, e.g. from the phone over Tailscale),
  but it's the ONLY agent — diagnostics + ollama-host fold into it, and the app
  just opens the UI/attaches. Best if you want Vera reachable when the Mac is
  logged in but the app isn't open.

**Recommendation: B** — Ankur uses Vera from his phone over Tailscale
([[project_vera_ios_parity]]), so a headless always-on brain matters. But it should
be ONE service that does everything, managed by one script, surfaced in the app.

## Migration (safe, staged — NOT YET)
1. **Don't touch the running brain.** Build + verify the unified service alongside.
2. Fold **diagnostics** into the brain as an internal scheduled task (it already has
   a scheduler pattern for proactive check-ins) → retire `install-diagnostics.sh`.
3. Fold **OLLAMA_HOST** into the brain's startup env → retire `ollama-host.plist`.
4. Make `desktop.py` (the app) the single entry: "ensure the one service is up,
   open the UI." One `install-vera.sh` installs/updates/removes the single agent.
5. Only AFTER the unified service passes its tests: bootout the old 3 agents.
6. Update the unified Settings (web/iOS) so one toggle controls it
   ([[project_vera_unified_settings]]).

## Risks / guards
- Brain is LIVE now — never leave Vera down mid-migration; cut over only when the
  new service is proven.
- The launchd brain runs a COPY under ~/Library/Application Support/Vera (the
  stale-code trap) — the unified installer must re-sync on every install.
- Keep a one-command rollback to the current 3-agent setup until confident.

## NOT in scope (resist sprawl)
Codepartner's reindex agent is SEPARATE and fine as-is (different project). The
app-updater agents (Comet/Google/Steam/Epic) aren't yours to manage. `unhosted`
daemon = the stalled project; disable separately if desired.
