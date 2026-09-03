# Vera as an agent — the roadmap to "Claude-level," safely

**Goal (Ankur):** Vera should work at the level of a capable coding/assistant
agent — plan, use tools, reach the internet, manage/connect/develop, run
autonomously *when told to* — **without** losing the founding guarantee that
makes Vera *Vera*: on-device, sealed, and **never acting on its own unless you
turn that on.** This doc is the architecture to get there, built piece by piece,
each one verified, no hollow shells.

> **The line (Ankur's call, this session):** *Vera reads + suggests; you act.*
> Power is added via **named, gated actions** (the amenity-booker pattern), never
> open-ended autonomy — with an **opt-in autonomous mode** for when you trust it.

---

## 1 · What already exists (the bones)

Vera is already further along than it looks:

| Piece | Where | State |
| --- | --- | --- |
| **Skill registry** (self-describing tools, LLM-callable) | `skills/base.py` | ✅ solid |
| **Local LLM backend** (Ollama / OpenAI-compatible) | `llm/` | ✅ |
| **Security kernel** (one sealed path: `write_state`/`append_line`) | `security.py` | ✅ |
| **Vault + device sync merge** (per-device keys, union/LWW) | `vault.py`, `sync.py` | ✅ |
| **Local HTTP server** (the app + extensions talk to it) | `voice/server.py` | ✅ |
| **Approval pattern** (dry-run default, per-action confirm) | amenity booker, `controls.py` | ✅ proven |
| **Read skills**: calendar (all accounts), contacts, rhythm, email triage, sentiment, places, activity | various | ✅ shipped |
| **Guarded net doorway** (allow-list + modes + sealed audit) | `net.py` | ✅ shipped |
| **Browser extension** (reads logged-in tab → local Vera) | `extensions/browser/` | ✅ shipped |

The gap to "Claude-level" is not the pieces — it's the **agent loop** that drives
them and the **permission layer** that keeps it safe.

---

## 2 · The permission model (the spine)

One idea governs everything: a **PermissionMode**, borrowed from how Claude Code
works.

```
read_only  → tools that only READ run freely. Nothing writes, sends, or leaves
             the machine. (The safe default for a new user / new task.)
approve    → acting tools run only after an explicit yes, one action at a time.
             Each shows exactly what it will do first. (The everyday default.)
auto       → allow-listed acting tools run without asking — the OPT-IN
             AUTONOMOUS MODE. Bounded by allow-lists + caps + a kill-switch.
```

- Every skill declares a **risk class**: `read` · `write_local` · `network` ·
  `act_external` (sends/books/posts). The mode + risk class decide whether it
  runs, asks, or is blocked.
- **Kill-switch**: a single call (`agent.stop()`) + a menu-bar toggle halts the
  loop and drops to `approve` immediately. Auto mode also has a **step budget**
  and **wall-clock budget** so it can never run away.
- **Everything is logged** to a sealed audit (`net.py` already does this; the
  agent loop extends it to every tool call). You can always see what Vera did.

This is the same shape as the booker's `booker_confirm` (dry-run default) —
generalised to every capability.

---

## 3 · The agent loop (the heart)

A Claude-Code-style **plan → act → observe** loop over the skill registry:

```
goal ─▶ [LLM plans: which tool, what args]
          │
          ▼
      permission gate ──(blocked / needs-approval / ok)──▶ you, or run
          │ ok
          ▼
      run skill ─▶ observe result ─▶ loop (until done or budget hit)
          │
          ▼
      summarise what was done + the audit trail
```

- Reuses `SkillRegistry.tool_specs()` (already OpenAI/Ollama tool-format) and
  `dispatch()`. The loop is the missing driver around them.
- **Bounded**: max steps, max wall-clock, and it always stops for an
  `act_external` tool unless mode is `auto` AND the action is allow-listed.
- Lives in `cognitive_twin/agent/loop.py`; the existing `voice/server.py`
  `/api/ask` becomes the single-shot case of the same loop.

---

## 4 · Capabilities, each as gated skills

Built on the loop + permission model, in priority order:

1. **Web (net.py)** — `web_fetch` (read), `web_download` (sandboxed, gated).
   *Shipped: the doorway. Next: register as risk-classed skills.*
2. **MCP server** — expose Vera's skills over the Model Context Protocol so
   **any MCP client (Claude, VS Code, …) can call them**. Read skills open;
   acting skills advertise their gate. `cognitive_twin/mcp/server.py`.
3. **VS Code connection** — a thin VS Code extension (the `vscode_drive` skill
   already sketches the sandbox) that talks to the local Vera: "ask Vera about
   this file," run a gated skill from the editor.
4. **Dev / manage** — run allow-listed dev commands in a project sandbox
   (build, test, git status) — the `vscode_drive` allow-list model, gated.
5. **CI/CD** — Vera can *report* CI status (read) and, gated, *trigger* an
   allow-listed workflow. Never secrets in the repo; tokens via the Keychain
   (`secrets_store`).
6. **Autonomous "away" mode** — the opt-in `auto` mode + a task queue Vera works
   through while you're away (the `anita-drive.sh` walk-away idea), inside all
   the budgets + kill-switch above.

---

## 5 · Health / life signals (the "understand my patterns" vision)

Read-only, on-device, feeding the rhythm picture:

- **Apple Health** (sleep/wake, workouts, **heart rate**) via HealthKit on the
  iOS/watch side → synced to the Mac core through the vault. *Strava data flows
  in via Apple Health, so it stays on-device — no Strava OAuth.*
- **Movement** (already: `activity.py`, `places.py`) — the auto-detected
  standing/walking/running + top places.
- **Google Timeline** — *only* via the user's own Takeout export (a file you
  drop in), never live scraping. Same honest stance as the DNA import.

These make Vera's suggestions *interesting* — grounded in your real day, not
guesses.

---

## 6 · What we DON'T do (the honest no's)

- **No live social scraping** (Instagram/Facebook) — breaks the on-device model,
  risks your accounts, against their ToS. Reachable only via *your* data exports.
- **No open-ended "download/act on anything."** Allow-lists always.
- **No deleting your real data** (contacts, files, repos) on Vera's own — Vera
  surfaces, you delete. (Hard rule.)
- **No secrets in the repo / on the wire** beyond the request itself.

---

## 7 · Build order (each shipped + verified before the next)

1. **Permission model + agent loop core** (`agent/loop.py`, `PermissionMode`) —
   the spine everything hangs on.
2. **Register net + a couple acting skills** through the loop, prove the gate.
3. **MCP server** — instant leverage (Vera's skills usable from Claude/VS Code).
4. **VS Code extension** — the editor surface.
5. **Health/rhythm enrichment** (HealthKit read, Timeline import).
6. **Autonomous "away" mode** — last, because it needs 1–4 rock-solid first.

Each step: builds, tests green, does what it says. That's the whole point — the
opposite of a stub pile.

---

*Vera stays true to its name (verus — true/faithful): on-device, sealed, honest
about what it can and can't do, and never acting behind your back. "Claude-level"
means the capability and the loop — not surrendering the guarantees.*
