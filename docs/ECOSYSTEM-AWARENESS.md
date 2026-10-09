# Ecosystem awareness — reading the room, so the conversation makes sense

> **Status:** DESIGN (not built). This document is the approach, for sign-off
> before any code. Nothing here ships until approved.
>
> **Why this exists (Ankur):** *"If the ecosystem difference is not understood,
> the chat and communication won't make sense."* Vera can feel, remember, and
> judge — but if she doesn't know **who you're talking to** and **what you're
> doing**, she'll answer when you weren't asking her, or talk over a meeting.
> Understanding the *situation she's in* is a precondition for everything else
> she does.

---

## 1. What she needs to understand

Two questions, every moment:

1. **Addressee — are you talking to _her_, or to someone else in the room?**
   A companion that replies to every sentence in the room is not present, it's
   intrusive. She should answer when addressed and stay quiet otherwise.

2. **Activity — what are you doing right now?**
   Watching a video, listening to music, on a call or in a meeting, heads-down
   working, or just here with her. Each changes what's appropriate: *don't
   interrupt a meeting; music is ambient, not a question to you; a video is your
   attention elsewhere.*

These combine into one small **Context** the brain can read — the same way the
occipital lobe already offers a face reading as *an observation with a
confidence*, never a fact.

---

## 2. First principle: this rides the existing perception pattern

We already have the right shape. The occipital `PerceptionEngine`
(`brain/regions/occipital.py`) takes an **optional cue source**, folds a reading
into the `Situation` as an *observation with confidence*, and — crucially — does
**nothing** when there's no sensor. Ecosystem awareness is the same contract,
widened:

```
sensors (app layer)  ──►  a cue dict  ──►  engine folds it into Signal.situation
  camera / mic / OS        {addressee, activity, confidence}      (never a fact —
  (all OPTIONAL)                                                   a weighted read)
```

The brain never opens a camera or reads an app list itself. The **app/OS layer**
owns every sensor; it calls a `perceive`-style callback that returns a cue or
`None`. No callback, no camera permission, mic off → the cue is `None` and Vera
runs **exactly as she does today**. (This mirrors `Brain(perceive=…)`.)

---

## 3. The signals (all on-device, all optional)

Each signal is independent and separately opt-in. Any subset can be off.

### Addressee — "talking to her vs the room"

| Signal | Source | What it tells us | Off-switch cost |
| --- | --- | --- | --- |
| **Face oriented to screen** | camera (Vision/ARKit, app layer) | you're looking at her, not across the room | no camera → unknown |
| **Lip movement ↔ speech timing** | camera + mic | the voice is *yours*, from the person facing her | degrades to voice-only |
| **Wake context** | her own state | you just addressed her / a reply is pending | always available |
| **Voice directed at device** | mic (on-device VAD + rough DoA if available) | speech aimed at the mic vs. ambient | degrades to text-only |
| **# of faces present** | camera | a second person in the room (ambient-talk likely) | no camera → assume 1 |

→ fused into **`addressed` confidence 0..1**. Below a floor, she **holds**:
listens, doesn't answer. (Text typed directly to her is always `addressed = 1.0`
— typing is unambiguous.)

### Activity — "what you're doing"

| Signal | Source | What it tells us |
| --- | --- | --- |
| **Foreground app** | OS (app layer; macOS `NSWorkspace`, etc.) | YouTube / editor / Zoom / Music… |
| **Now-playing** | OS media remote (already modelled by `music.py`) | music vs. a video vs. nothing |
| **Mic/camera in use by another app** | OS | you're in a **call / meeting** → hold back hard |
| **Call/Do-Not-Disturb / Focus** | OS | your own stated "not now" |

→ fused into an **`activity` label** + a **`should_interject` gate**
(e.g. `meeting` or `call` ⇒ she never speaks unprompted; `music` ⇒ ambient, fine;
`video` ⇒ your attention is elsewhere, keep it short).

> Honesty rule (same as the face reading): a guessed activity is offered *with a
> confidence*, never asserted. Unknown is a valid, common state and must behave
> gracefully — when she can't tell, she defaults to **polite restraint**, not
> guessing.

---

## 4. Where it lives in the brain

Perception sits before parietal/limbic, so context colours the whole turn:

```
occipital (face)  →  ECOSYSTEM (addressee + activity)  →  parietal → limbic → …
```

- A new cue source `Brain(sense_context=<callable>)` (sibling to `perceive=`),
  returning `{addressee: {...}, activity: {...}}` or `None`.
- Folded into `Signal.situation.facts` as `addressed`, `activity`,
  `should_interject`, each with a confidence — **read, never written to disk by
  the engine**.
- **Frontal** reads `should_interject`: a meeting/low-addressed turn ⇒ stance
  becomes *hold / stay quiet*. **Cerebellum** can soften/again-not-speak.
- Proactive/ambient features (if any) must check `should_interject` **first**.

This is additive: with no `sense_context`, the field is absent and nothing
changes.

---

## 5. Privacy model (the part that has to be right)

This feature reads a camera, a microphone, and what app you're using — the most
sensitive inputs in the system. It must obey the existing security kernel
([[project-vera-security-kernel]], `cognitive_twin/security.py`) and add nothing
that bypasses it.

1. **On-device only, always.** All inference (face orientation, VAD, app read)
   happens locally. **No frame, no audio, no app name ever leaves the machine**,
   ever — not even to the local model unless the user turns that on explicitly.
   This belongs in the egress allow-list review as **"no new egress."**
2. **Opt-in per sensor, off by default.** Camera-addressee, mic-direction, and
   activity-sensing are three separate switches, all starting **off**. Vera is
   fully functional with all three off.
3. **Ephemeral by default.** The raw signals (a face is oriented; app = Zoom) are
   **transient** — used for the turn, not stored. If any *derived* summary is ever
   persisted (e.g. "usually heads-down 9–11am"), it goes through
   `security.write_state` **sealed**, is registered in `STATE_STORES`, and is
   covered by `security doctor` — the same rule that caught the tone/mirror
   plaintext leak. **Default: persist nothing.**
4. **The halt flag covers it.** The one flag that halts every outward/mutating
   capability also disables all sensors here.
5. **Visible + revocable.** When a sensor is live, the app shows it (a dot), and
   one switch turns it off. No silent watching.
6. **Fail-soft is a feature.** Sensor error, permission denied, unknown state →
   `None` → she behaves as today. A failed sensor never breaks the mind (exactly
   as occipital already does).

A `security doctor` check will assert: sensors default off, no new egress, no raw
frame/audio written, any derived store sealed + in `STATE_STORES`.

---

## 6. Build order (once approved)

1. **Activity sensing, no camera** — foreground app + now-playing (`music.py`
   already reads media) + call/mic-in-use → `activity` + `should_interject`.
   Frontal honours it. *Biggest value, lowest privacy cost — she stops talking
   over your meeting.*
2. **Addressee from voice + wake context** — VAD + "a reply is pending" →
   `addressed` confidence, mic only.
3. **Addressee from camera** — face-oriented-to-screen + face count, extending
   `PerceptionEngine`. Highest sensitivity, last.
4. **Make it visible** — surface the live `Context` in the Mind view
   (`viz.py`), the same way the limbic net + RAG are now shown, so you can *see*
   her decide "you're in a meeting — I'll wait."

Each step: on-device, opt-in, fail-soft, sealed if persisted, tests green,
`security doctor` SAFE. Nothing pushed without the usual explicit go.

---

## 7. Open questions for Ankur

- **Which OS first?** macOS (NSWorkspace / MediaRemote / Focus) is the primary;
  iOS sensors differ (ARKit strong, app-list restricted). Start macOS?
- **Proactivity:** does Vera ever speak *unprompted* based on context (e.g. "you
  seem heads-down, I'll be quiet"), or only ever change how she responds when you
  *do* address her? (Default assumption: **reactive only** — she adjusts, never
  initiates — unless you want gentle proactivity.)
- **Storage:** persist any long-run patterns (your rhythms by activity), or keep
  everything strictly ephemeral? (Default: **ephemeral**.)
