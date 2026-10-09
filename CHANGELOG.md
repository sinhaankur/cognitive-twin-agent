# Changelog

All notable changes to Vera. Format loosely follows [Keep a Changelog](https://keepachangelog.com);
versions are the app's `CFBundleShortVersionString`.

## [Unreleased] — iOS parity

Bringing the iOS (Anita) app toward the mature macOS app, shipped as small
version-controlled increments.

### Added (iOS)
- **Settings & Privacy screen** — where she thinks (model host + model), her
  presence (3D likeness toggle, persona), and privacy (remembered-count +
  forget-everything with confirm). Phone-shaped; no desktop-only installers.
- **Crafted top-right menu** — one control (a soft monogram chip) opening a glass
  sheet with an identity header + grouped rows, replacing three bare icons. Its
  own look, matching the Siri-orb world.
- **Model host, end-to-end** — the Rust core reads `CTWIN_OLLAMA_HOST`
  (host or host:port; blank = localhost), set from the persisted host in
  Settings, so a phone can reach an Ollama on a machine you own over the tailnet.
  ABI-stable (no C signature change). +3 core tests.
- **ATS for local networking** — iOS blocks cleartext HTTP by default; added
  `NSAllowsLocalNetworking` (local/tailnet only, not arbitrary loads) so the
  http Ollama connection actually works.
- **Test connection** in Settings + a **live reachability dot** on the main
  screen (green/orange + label), matching the macOS status indicator.

## [0.3.1] — 2026-10-07

A stability release: chat was hanging and, once unstuck, every reply took 55-70s.
Both are fixed — replies now land in ~6s (the real cost of the local model), and
the app can no longer be frozen by a stalled voice worker.

### Fixed
- **Chat no longer hangs.** The neural-voice (Kokoro) worker was read with a
  blocking call that had no timeout, so a stalled worker wedged the server forever —
  and because it held a lock, every later message hung too. Reads are now bounded;
  a stuck worker is killed and restarted, and Vera falls back to the system voice
  instead of freezing. Speech is a nicety; answering is not.
- **Replies are ~10× faster.** Every turn was decrypting the *entire* device-activity
  log (tens of thousands of sealed lines, ~6s) and re-reading the sealed life-memory
  index (~3.5s) just to build the prompt. Now: the activity summary reads only the
  recent tail and is cached by file signature; the life-memory index is cached the
  same way; the RAG query is embedded once and reused across all indexes; and the
  life-memory re-index runs in the background instead of blocking the reply. These
  caches are warmed at startup so even the first reply is fast.
- **Sharable twins export again.** `export_twin` crashed on a `UnicodeDecodeError`
  once personas were sealed at rest (it read the encrypted file as text). It now
  decrypts through the security kernel, writes a *portable* plaintext persona into
  the package, and re-seals it on import — so a shared twin is sealed on the
  receiving machine too, never left as plaintext.

## [0.3.0] — 2026-10-06

A big release: a real human voice, a resilient architecture, and a companion that
understands more of your life — all still fully on-device.

### Added
- **Neural voice (Kokoro).** Vera now speaks in a warm, expressive, human-sounding
  voice (Bella by default) instead of a robotic system voice — bundled, on-device,
  no macOS voice download. 12 selectable female voices.
- **Life Story from photos.** She understands your recent life: places you've been,
  and *moments* (a full Saturday in Pune, an evening out) — so she can recap your
  weekend or where you've been. Opt-in, metadata only, nothing uploaded.
- **Places you've been.** Visited places derived from photo location metadata.
- **Personality dials.** Settings → Personality: Warmth, Humor, and Playfulness
  (nerdy) sliders that shift how she expresses herself without changing who she is.
- **Native voice picker** with preview + a "get better voices" path.
- **File attach** in chat (PDF/text/code, read on-device as context).
- **PRIVACY.md** — the privacy posture, mapped to the principles and proven green.

### Changed
- **Premium chat redesign.** Her replies read as clean, generous text with a gold
  accent (not a loud bubble); your messages in a soft bubble; a warm empty state;
  refined header, input, and motion.
- **Text-first chat.** Replies are text by default; she speaks only when you ask
  (or when you talk to her by voice). Markdown-rendered.
- **Runs as a launchd service.** The brain is kept alive by the OS (restarts on
  crash, starts at login, always reachable) — the app just connects.
- **Conversation memory.** She carries the thread, so short follow-ups make sense.
- **Lighter footprint.** One right-sized model per machine, idle models evicted;
  trimmed the local model set from ~24 GB → ~9.4 GB.
- **Better RAG relevance.** Adaptive hybrid scoring + a relevance floor so
  off-topic queries no longer pull in filler passages; per-source diversity;
  sentence-aware chunking.
- **The Mind** view is now a calm, legible thinking pipeline (not a noisy galaxy).

### Fixed
- **"Brain not reachable."** Root cause was `~/Documents` being TCC-locked for
  background processes; the service now runs from a non-TCC location.
- **False "microphone is off" banner.** It now reads live permission state, names
  the actual missing permission (mic vs speech), and clears itself when granted.
- **"Mic isn't working" / wake word.** A visible, actionable permission banner
  instead of a silently-dead mic.

### Security / Privacy
- Sealed two at-rest leaks (soul/persona were writing plaintext); `security
  doctor` now fully green. No telemetry; one fenced network door; a kill switch.
- Confirmed Vera does **not** disable Siri.

## [0.1.0] — earlier

- Initial local-first agent: Ollama model, skill system, bounded tool-calling
  loop, persona, model routing, CLI, floating orb app on Mac + iOS.
