# Vera control surface — brand + UX (the one source of truth)

Ankur: *"this can be a switch like Tailscale"* + *"refer the UI/UX of Tailscale so
we match the quality"* + *"rethink UI/UX and color branding — use what is unique
and professional"* + *"we want the user to be in control for sure."*

So: **Tailscale-quality control**, but **Vera's own identity** — not a teal clone.

## The identity (chosen)
Vera's existing site accent is warm gold/amber (`#c8992e`, see the Lab page +
vera-brain diagram). The control surface stays in that world: **warm, human,
professional** — right for a cognitive twin, and unique against every teal/green
"security app."

### Tokens
| Token | Value | Use |
|---|---|---|
| `--vera-panel` | `#0b0b0d` | deep near-black panel background |
| `--vera-ink` | `#ECE7DD` | primary text (warm off-white) |
| `--vera-muted` | `#8A857B` | secondary text / captions |
| `--vera-accent` | `#c8992e` | **signature amber** — the switch, active state |
| `--vera-accent-soft` | `#e0a34b` | hover / glow of the accent |
| `--vera-danger` | `#c0484a` | **muted red — DANGER ONLY** (lockdown) |
| `--vera-line` | `#23211d` | hairlines / dividers |

Rule: **red means danger, nothing else.** Amber is the brand; everything else is
neutral ink on near-black.

## The four understood states (what the colors MEAN)
| State | Icon | Color | Meaning (plain language) |
|---|---|---|---|
| Private | 🔒 | neutral ink | Only this Mac can reach Vera. The safe default. |
| My devices | 📱 ● | amber glow | Your devices reach her over Tailscale, token-gated. |
| Safe Mode | ◉ | soft amber | Reads/chats freely; asks before any action. (default ON) |
| Lockdown | 🚫 | muted red | Kill switch — she can't reach out or act. Think only. |

## UX principles (matched to Tailscale's quality bar)
1. **One glance = full truth.** The top line always states who can reach Vera and
   whether she can act. No hunting. ("privacy mode needs to be understood.")
2. **The user is in control, for sure.** Every reach/act change is an explicit
   toggle the user flips; nothing widens itself. Changes are logged (audit).
3. **Fail-safe, always.** Unknown state = most private + most locked. The kill
   switch overrides everything. Safe Mode is ON by default.
4. **Plain words over jargon.** "Only this Mac" not "127.0.0.1 bind". The machinery
   is hidden (the whole product thesis) but the *consequence* is explained.
5. **Developer section is opt-in + folded away.** Ports, tokens, bind host, model
   backend live under "Developer ▸" for power users — never in the default view.

## Surfaces (all consistent, same tokens)
- **Menu bar** (primary, Tailscale-style): status line + reach switch + Safe Mode +
  Kill Switch + Developer submenu. `cognitive_twin/voice/menubar.py`.
- **Web settings** (`/settings` in the local UI): the fuller panel (device list,
  audit, developer). Mirrors the menu bar.
- **Public Lab page** (sinhaankur.com `/lab/cognitive-twin`): tells the story —
  local, private, user-in-control, your AI when the cloud is gone.

## The backup story (why this matters — Ankur lived it)
Ankur lost cloud-AI access for 2 days. Vera is the **local backup**: no
subscription, no cloud, works offline. The control surface should make that
legible — "Vera is here even when the cloud isn't." A quiet strength, not a slogan.
