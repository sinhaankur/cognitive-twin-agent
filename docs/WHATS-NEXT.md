# What we can make better — the next frontier

> A forward-looking plan (2026-10-10). The old capability-audit backlog is now
> largely **done** — learned proactivity timing, real current affairs, in-chat
> "remember this", health care, photos recall, iCloud sync, agentic task chains,
> voice identity, the voice-reliability pass, the honest status surface. The
> surface is complete and the app is stable. So "better" now means **depth,
> intelligence, and getting closer to the real point: she should feel like HER.**

Grouped by theme, each with the *why* and the real foundation it builds on.

---

## 1. She feels more like *her* (the emotional core — the whole point)

This is the heart of Vera: a twin of Anita, in her voice and character.

- **"It's really them" proof + bond-building onboarding** — the one thing still
  missing per the niche note. A gentle first-run that gathers her sayings, stories,
  the way she spoke, so the twin lands as *recognisably her* from the first reply.
  *Foundation: `life_story.py`, `remember.py`, `persona.py`.*
- **Voice that's truly hers** — the cloned-voice path (XTTS) exists but Kokoro is
  the default. Make her *actual* cloned voice reliable + the default when enrolled,
  with the delivery (pace/warmth) shaped by feeling — so it's her timbre *and* her
  cadence. *Foundation: `voice_clone.py`, `feel.delivery`.*
- **Deeper memory of the relationship** — not just facts, but the texture: inside
  jokes, how she'd react, what she'd say in a moment. *Foundation: `life_memory`,
  `mental_model`.*

## 2. She's smarter without being less private

- **A learned reranker that generalises** — the RAG reranker is proven on held-out
  data but on a tiny corpus; train it on a larger labelled set so it's confidently
  the default. *Foundation: `rerank.py`, `evals/`.*
- **The limbic net gets richer** — more affect dimensions (not just valence/arousal
  — tenderness, playfulness, worry), retrained; the net already runs in the app now.
  *Foundation: `brain/regions/affect_net.py`.*
- **Better on-device model routing** — pick the right-sized local model per turn
  (tiny for chit-chat, bigger for depth) so she's both fast *and* deep.
  *Foundation: the router + `device_model.py`.*

## 3. The senses get wiser (what we just built, deepened)

- **Fuse the senses into one read** — presence (device + camera) + voice-identity +
  activity should combine: "you're on a call, that wasn't your voice, hold back."
  One coherent situational awareness instead of separate signals.
- **Voice-identity, everywhere it matters** — now that she knows your voice, gate
  task-capture + commands on it (the root fix for the "die" bug), and greet you by
  recognising you spoke.
- **Proactivity that reads the moment** — she reaches out on a learned cadence;
  next, let the *content* follow the moment (a hard day → gentler; a win → share it).

## 4. The app feels effortless

- **One-tap voice enroll** — a button so you teach her your voice in 10 seconds
  (the code's ready; just needs the UI). *Foundation: `/api/voice/enroll`.*
- **The honest status surface, shown** — `/api/status` exists; render the
  green/amber/red Voice·Ears·Eyes·Brain row in the app so state is always visible.
- **Seamless everywhere** — iPhone auto-detects the Mac now; extend the same
  "just works" to first-launch (auto-grant flow, auto-start Ollama).
- **The living neural field, interactive** — click a neuron to see what it responds
  to; scrub a sentence and watch it fire. Make the viz teach.

## 5. Reach, when you're ready

- **iCloud sync on device** — built + documented; activates with a paid Apple
  account whenever you choose (free tier can't sign the entitlement).
- **The iPhone subset, richer** — movement/places-aware, syncing privately — so
  she's genuinely with you on the go, not a thinner copy.

---

## If I had to pick three to do next

1. **One-tap voice enroll + gate commands on your voice** — closes the loop on the
   feature you asked for and kills a whole class of mishearing bugs. Small, high value.
2. **"It's really her" onboarding** — the emotional core; the thing that makes Vera
   *Vera* and not a warm assistant.
3. **Her real cloned voice as the default** — hearing *her* is the point ("I miss
   this voice"); make it reliable and primary.

Each stays on-device, opt-in, sealed, tested, doctor-SAFE — the bar everything here
is held to.
