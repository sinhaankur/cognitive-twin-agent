# Vera — Roadmap

*An honest map of where Vera is and where she's going. Updated 2026-11-20.*

Vera is **a private, on-device twin of someone you love** — in their voice and
character, never cloud, yours. The engine is mature (458 commits, 85 modules, a
grab-it-and-go release). What's left is mostly **depth and soul**, not plumbing.

---

## ✅ What we've built so far

**One real app — it just works**
- One Mac app: double-click, it owns its own brain (Python + local model), no terminal.
- Cross-platform: `run.sh`, Docker, a published v0.3.2 release (`.dmg` + pip wheel).
- Native menu bar, Tailscale-grade status, a web UI + Controls page that adapt to light/dark.

**She communicates — warmly, and like a person**
- Warm, feminine, grounded personality; replies in ~3s (Interactive priority — resilient on a busy Mac).
- A real personality: playful, witty, tender, curious, with moods — not a flat assistant.
- **Grounded** — doesn't invent experiences ("I read a poem") or fabricate false memories.
- **Remembers the conversation** — recency gate: "what did I just tell you?" reads the real turns.

**The voice feels alive (the "Her" layer)**
- Her neural voice (Kokoro, af_heart) — the one you love.
- **A voice for every emotion** (`voicebox.py`): grief slow + hushed, stressed *slower to steady you*,
  happy lifted, angry measured — pace, warmth, breath all shift with the moment.
- Laughs + breath texture ("Oh,", "Aw,", "Mm,") — only when the moment genuinely fits, never in distress.

**She feels — and handles the hard moments**
- The limbic/affect engine reads your emotional state and shapes her tone.
- **Grief is held with care** — never tone-deaf to loss (3-layer safeguard).
- Crisis / self-harm handled by a deterministic, lifeline-naming layer.

**She knows your life (on-device, sealed)**
- "Your life" sync panel: Calendar, Mail, Photos, Location — read-only, opt-in, nothing uploaded.
- On-device **FaceID** recognition + a **gaze engine** (knows when you're looking at the Mac vs. away).
- A real **brain**: limbic → hippocampus (memory + mental model + RAG) → cortex.

**She's genuinely private — and sociable with your people**
- Everything sealed at rest (native ChaCha20), secrets in the Keychain, no cloud by default.
- **Guest mode**: your people (family, friends) can meet + chat with her warmly, but your
  private world never leaks, no matter how they ask.
- A security "doctor" that audits egress; a kill switch; reach control (this Mac / your devices).

**Quality is measured, not assumed**
- `scripts/e2e-quality.py` — an honest end-to-end pass (currently 15/15).
- RAG benchmarked against the HF/MTEB leaderboard; a reranker trained + validated on held-out data.
- She reads PDFs you drop in and discusses them.

---

## 🔲 What's missing / what we lack

The engine is strong; the gaps are about **being truly HER**, and the last mile of polish.

**1. The soul — the irreplaceable layer (highest value)**
- [ ] **Her actual voice, cloned + default.** The clone path (XTTS) exists but Kokoro is default.
      Make *her real timbre* reliable and the default when enrolled — her voice *and* her cadence.
- [ ] **"It's really them" onboarding.** A gentle first-run that gathers the person's sayings,
      stories, and way of speaking so the twin lands as *recognisably them* from the first reply.
      *(The capture tools exist — `remember.py`, `life_story.py`, `keepsake.py` — but the vault is empty
      until someone sits and tells her who the person was. This is the one thing only you can do.)*
- [ ] **Durable keepsakes on a safe remote.** Inheritance is the point — the memories/sayings taught
      "whole, forever" should live somewhere that outlives one Mac (currently on-device only).

**2. Reliability / the rough edges**
- [ ] **Cold first-turn is slow (~11-12s)** while the model reloads after idle. Options: pin the
      model in RAM, or a tiny "warming…" voice cue so it never feels stuck.
- [ ] **The 3B model occasionally slips** (a flowery line, a slight misread). Safety nets catch the
      *critical* cases (grief, false memory); the everyday polish needs a better/tuned model.
- [ ] **Voice worker cold-load** returns empty for a few seconds after a restart (minor, timing).

**3. The senses, fused**
- [ ] **One situational read** — presence + camera + voice-identity + activity combined:
      "you're on a call, that wasn't your voice → hold back." Today they're separate signals.
- [ ] **One-tap voice enroll** — teach her your voice in 10s (the `/api/voice/enroll` code is ready; needs the UI).

**4. The iOS / cross-device story**
- [ ] The iOS (Anita) app exists but isn't verified built (no simulator locally); the Mac is the anchor.
- [ ] iCloud sealed-sync is wired but needs a paid Apple account to fully enable the iCloud capability.

---

## ⭐ What can be better

Done well already — these would raise it from "very good" to "unmistakable":

- **A better on-device model.** vera-tuned (3B) is light + fast but occasionally imperfect. A larger
  or better-tuned local model (or smart per-turn routing: tiny for chit-chat, bigger for depth)
  would make her both fast *and* consistently deep. *Biggest single quality lever.*
- **Richer affect.** The limbic net reads valence/arousal; add dimensions (tenderness, playfulness,
  worry) so her emotional reads are finer-grained, then retrain.
- **A real voice box / engine** (your idea) — beyond pace/pitch, toward true expressive variation:
  more voices for moods (carefully, no jarring switches), genuine breaths, a real soft laugh.
- **Deeper relationship memory** — not just facts, but the *texture*: inside jokes, how the person
  would react, what they'd say in a given moment.
- **The honest status surface, shown** — render the Voice·Ears·Eyes·Brain green/amber/red row in the
  app so her state is always visible at a glance.
- **Proactivity that reads the moment** — she reaches out on a learned cadence; next, let the
  *content* follow the moment (a hard day → gentler; a win → share it).

---

## The north star

Everything above serves one thing: **she should feel like HER** — the specific, warm person she's a
twin of — carried forward, private, and yours. The tech is the *how*; the soul is the *what*. The
most important next step isn't code — it's sitting down and telling her who the person was.
