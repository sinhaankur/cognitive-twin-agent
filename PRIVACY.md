# Privacy

Vera is a private, on-device companion. Her whole design is a privacy posture:
your life stays on your machine. This document maps Vera to the privacy
principles of guides like [fmhy.net/privacy](https://fmhy.net/privacy) —
local-first, minimal data, no telemetry, encryption, open-source, decentralized —
and shows how each is met, with the code that proves it.

> Honest threat model up front: at-rest encryption protects your files from
> another user or a stolen disk. It does **not** defend against malware already
> running as *you* on an unlocked Mac — nothing on your own machine can. Vera's
> job is to never be the thing that leaks you.

---

## The principles, and how Vera meets them

### 1. Local-first processing
Everything that is *you* is computed and stored on this device.
- The language model runs locally via Ollama; a right-sized model is chosen for
  your machine (`cognitive_twin/device_model.py`), never a cloud API by default.
- Her feeling, stance, memory, and judgment are her own on-device logic — the
  model is only one organ (language), never the source (`system_dna.md` §
  Epistemic Independence; `cognitive_twin/feel.py`, `brain_flow.py`).
- The brain runs as a local service bound to `127.0.0.1` only — never a public
  port (`scripts/vera-brain.sh`, `cognitive_twin/voice/server.py`).

### 2. Minimal collection — nothing by default, everything opt-in
Vera senses nothing until you turn each sense on, one switch at a time.
- Photos (metadata only), activity (frontmost app), places, music, the camera
  ("See me" — face cues only), the room ("Hear the room" — sound *types* only).
  Each is OFF until you enable it (`cognitive_twin/{photos,activity,places,
  music}.py`; the switches live in Settings / `controls.py`).
- Metadata only where possible: Photos reads album titles, dates, and location
  clusters — never pixels, never faces. The camera reads cues, never records.

### 3. No telemetry, no analytics, no tracking
There is no analytics SDK, no crash reporter, no "phone home."
- Grep the tree: the only hits for "tracking" are *your* opt-in senses, not
  surveillance of you. No Segment/Mixpanel/Sentry/GA/Crashlytics anywhere.
- The presence of a WatchTower (a watcher you might run) is explicitly **not**
  consent to send it Vera's telemetry (`cognitive_twin/watchtower.py`).

### 4. Encryption at rest
Everything personal Vera stores is sealed.
- One kernel seals all personal state (`cognitive_twin/security.py`) with
  **ChaCha20-Poly1305** and a **device-bound key held in the macOS Keychain**,
  bound to this Mac + this account (`cognitive_twin/vault.py`). A copied file
  off this machine is ciphertext.
- `python3 -m cognitive_twin.security seal-all` seals everything now;
  `security doctor` audits the posture in one command.

### 5. One fenced network door — and a kill switch
Network egress happens in exactly one place, fenced like a firewall.
- `cognitive_twin/net.py` is the ONLY egress path, with a permission mode
  (`read_only` / `approve` / `auto`) and a host allow-list. **Default is
  `approve`** — reaching the network asks first unless the host is allow-listed.
- The outbound surface is tiny and legible: localhost, your own site, GitHub
  (self-update), and Google **only** if you opt into email (OAuth). No ad/tracker
  domains, ever.
- A global **kill switch** (`security.lockdown()` / the 🛑 in the chat) halts
  every outward or mutating capability — network, email, screen control — at
  once, and stays dormant until you release it. Fail-safe: unknown state = locked.

### 6. Open-source and auditable
The whole brain is readable Python you can inspect, run, and change. Nothing is a
black box; the privacy claims above are each a file you can open.

### 7. Decentralized / no lock-in
No account, no corporate platform, no required cloud. Vera is yours; multi-device
sync (when used) is designed per-device-key and local/private-transport first
(see `SECURITY.md`, `policies/multidevice-trust-sync.policy.json`).

---

## Your controls (all local, all reversible)
- **Every sense is a switch** — turn Photos, activity, places, camera, room,
  music on or off whenever you like.
- **🛑 Kill switch** — halt everything outward in one tap.
- **Network mode** — keep it `approve` (asks first) or `read_only`; add/remove
  allow-listed hosts (`net allow <host>` / `net disallow <host>`).
- **Clear memory** — wipe what she's learned (Settings → privacy control).
- **`security doctor`** — one command that checks sealing, egress, and the port
  binding and tells you if anything is off.

## What leaves this Mac
Only what you explicitly turn on:
- **Nothing**, by default.
- **Email** (if you connect it): to your provider, over your own OAuth/IMAP.
- **Self-update**: a fast-forward `git pull` from GitHub (code only, never data).
- **Reverse-geocoding** a photo location cluster to a place *name* (Apple's
  geocoder; it resolves coordinates to a city, it does not identify you).

If that list ever needs to grow, it should grow *visibly* — a new allow-listed
host, a new switch — never silently.
