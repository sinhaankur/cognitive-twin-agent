# Vera — the brain architecture

> Vera should feel human because she is built like a mind: distinct regions, each
> with its real function, wired together — not one model with a warm voice bolted
> on. "Robotic" is what you get when the regions are missing or disconnected.

This maps Vera's engines onto the **real functions of brain regions** (kept
truthful to neuroanatomy — the mapping is a faithful analogy, not decoration) and
onto the **five faculties** Ankur named: Memory · Humor · Perspective · Emotion ·
Voice. Design first; this doc is the target, code follows it.

---

## The regions → engines

```
                        ┌───────────────────────────────────────┐
                        │           FRONTAL LOBE                  │
                        │  Perspective · judgment · planning ·    │
                        │  the "self" that decides and has a POV  │
                        │  → PerspectiveEngine + Router/Council    │
                        └───────────────┬───────────────────────┘
                                        │ decides, holds a stance
   ┌────────────────────┐   ┌───────────▼───────────┐   ┌────────────────────┐
   │  PARIETAL LOBE     │   │   CEREBRAL CORTEX      │   │  LIMBIC (emotion)  │
   │  situational sense │   │  reasoning + language  │   │  feeling + tone    │
   │  where/when you    │   │  the LLM reasoning +    │   │  → EmotionEngine   │
   │  are, your day     │   │  the sulci (folds) =    │   │  (soul + mood,     │
   │  → Rhythms/Shadow/ │   │  DEPTH of thought       │   │  promoted)         │
   │    Activity/Places │   │  → CortexEngine (router │   │                    │
   └─────────┬──────────┘   │    + reasoning models)  │   └─────────┬──────────┘
             │              └───────────┬────────────┘             │
             │ context                  │ words                     │ colour
             ▼                          ▼                          ▼
   ┌────────────────────┐   ┌────────────────────────┐   ┌────────────────────┐
   │  HIPPOCAMPUS       │   │   TEMPORAL / HUMOR      │   │   CEREBELLUM       │
   │  memory formation  │   │   wit, timing, play     │   │  smooths + times   │
   │  + recall          │   │   → HumorEngine         │   │  DELIVERY: paces,  │
   │  → MemoryEngine    │   │   (new)                 │   │  coordinates the   │
   │  (memory.py)       │   │                         │   │  final voice/reply │
   └────────────────────┘   └────────────────────────┘   │  → VoiceEngine +   │
                                                          │    delivery timing │
                                                          └────────────────────┘
```

### FRONTAL LOBE — Perspective / executive self  → **PerspectiveEngine** (new)
Real function: judgment, planning, personality, having a point of view. This is
what makes a reply feel like *a person with a stance*, not an assistant. It reads
Ankur's `persona.json` (values, dislikes) + memory and gives every answer a
POINT OF VIEW — an opinion, a recommendation, a "I'd actually do X because Y",
not neutral hedging. Works with the existing **Router/Council** (which already
decides *which model* and could decide *which stance*).
_Faculty: Perspective._

### CEREBRAL CORTEX + SULCI — reasoning + language depth  → **CortexEngine**
Real function: higher reasoning + language. The **cerebral sulci** (the folds)
are what pack more cortex into the skull — literally "depth of thinking". So:
the cortex = the reasoning models (qwen2.5:7b / 14b) via the router; the sulci =
the *depth* dial — how hard Vera thinks (fast surface reply vs. the 14b deep
planner + `think_routes` multi-step reasoning). Already largely built (router +
loop); formalise the "depth" as a first-class knob.
_Faculty: (substrate for all — language + reasoning.)_

### PARIETAL LOBE — situational awareness  → SituationEngine (exists, unify)
Real function: integrates the senses into *where and when you are*. Vera already
has this scattered: **Rhythms** (your day/sleep/work), **Shadow** (your tasks),
**Activity** (how you work), **Places** (where you are), **projects_db** (what
you're building). Unify these into one situational read the other engines share.
_Faculty: feeds Perspective + Memory._

### LIMBIC SYSTEM — emotion  → **EmotionEngine** (promote soul + mood)
Real function: feeling, and colouring everything else with it. Vera has **mood.py**
(tone) + **soul.py** (evolving character) — promote them into one EmotionEngine
that (a) reads the emotional register of what Ankur says, (b) sets Vera's own felt
state, and (c) EXPORTS that state to Humor (when to be light), Perspective (gentle
vs. blunt), and Voice (warm vs. brisk delivery). This is the missing "connective
tissue" that makes the engines feel like one being.
_Faculty: Emotion._

### HIPPOCAMPUS — memory  → **MemoryEngine** (memory.py, ✅ works)
Real function: forming + recalling memory. Already built and verified: private,
on-device, sealed, self-compacting (maintenance). It feeds Perspective (who you
are), Situation (your projects), and Humor (callbacks to shared history — the
funniest lines reference something real).
_Faculty: Memory._

### TEMPORAL / association cortex — humor  → **HumorEngine** (new)
Real function: wit lives where language, memory, and emotion meet. A HumorEngine
that, when the moment allows (Emotion says it's light, not a serious/sad turn),
adds real wit: a callback to a shared memory, a dry aside, playful timing — never
forced, never a joke-bot. Gated by Emotion so it never quips during a hard moment.
_Faculty: Humor._

### CEREBELLUM — coordination + timing  → **VoiceEngine** + delivery
Real function: the cerebellum doesn't originate movement — it makes it *smooth,
timed, coordinated*. Perfect fit for delivery: the VoiceEngine (XTTS, just tuned
less-robotic) plus the PACING/timing of the final reply — pauses, emphasis,
speed — shaped by Emotion (calm vs. excited) so the voice matches the feeling.
_Faculty: Voice._

---

## How they connect (the wiring that kills "robotic")

One turn flows through the brain, each region shaping the next:

```
 you speak
   │
   ▼
 PARIETAL  → situational read (your day, projects, place)
   │
   ▼
 LIMBIC    → reads the emotional register + sets Vera's felt state ──┐
   │                                                                  │ (colours everything)
   ▼                                                                  │
 HIPPOCAMPUS → recalls what's relevant (shared history)              │
   │                                                                  │
   ▼                                                                  │
 FRONTAL   → forms a POINT OF VIEW (persona + memory + situation) ◄──┤
   │                                                                  │
   ▼                                                                  │
 CORTEX    → reasons + drafts the words (model, depth via sulci)     │
   │                                                                  │
   ▼                                                                  │
 TEMPORAL  → adds wit IF emotion says it's a light moment  ◄─────────┤
   │                                                                  │
   ▼                                                                  │
 CEREBELLUM→ paces + delivers; VOICE tone matches the feeling ◄──────┘
   │
   ▼
 Vera speaks — as a person, not a product
```

**The key insight:** the voice sounded robotic because the *upstream* regions
(perspective, humor, emotion→voice coupling) weren't there to give the words a
stance, a warmth, a reason to vary. Fix the brain and the voice follows.

---

## Faculty ↔ region map (Ankur's five)

| Faculty | Region | Engine | State |
|---|---|---|---|
| Memory | Hippocampus | MemoryEngine (`memory.py`) | ✅ works |
| Humor | Temporal/association | HumorEngine | ❌ build |
| Perspective | Frontal lobe | PerspectiveEngine | ❌ build |
| Emotion | Limbic | EmotionEngine (`soul`+`mood`) | 🟡 promote + connect |
| Voice | Cerebellum (delivery) | VoiceEngine (`voice_clone`, XTTS) | ✅ tuned |
| _(substrate)_ | Cortex + sulci | Router + reasoning loop | ✅ works |
| _(context)_ | Parietal | Situation (rhythms/shadow/activity/places) | 🟡 unify |

---

## Build order (after this design is signed off)

1. **EmotionEngine** first — it's the connective tissue every other engine reads.
   Promote `soul`+`mood`: read Ankur's emotional register, set + export a felt state.
2. **PerspectiveEngine** — give replies a real POV (persona + memory + situation).
3. **HumorEngine** — wit gated by Emotion, fed by Memory.
4. **Wire the flow** in the agent loop: parietal → limbic → hippocampus → frontal
   → cortex → temporal → cerebellum, each shaping the reply + the voice's tone.
5. **VoiceEngine coupling** — let Emotion drive XTTS delivery (already tuned; make
   temperature/speed a function of the felt state, not a constant).

Each engine: small, local, testable, honest — the same bar as the rest of Vera.
Nothing invented as fact; emotion/humor are Vera's own felt responses, never
claimed knowledge she doesn't have.
