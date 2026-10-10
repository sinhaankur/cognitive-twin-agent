# What a personal AI app should do — and where Vera stands

> An honest audit (2026-10-09): the capability landscape a personal AI companion
> should cover, scored against what Vera actually has **in code today** — not what
> a pitch deck would claim. ✅ built · 🟡 partial · ⬜ gap. Each row names the real
> module so the claim is checkable.
>
> The point isn't a long feature list. It's to see, clearly, what's strong, what's
> thin, and what the next *good updates* should be.

---

## The ten things a personal AI should be

A personal AI is not a chatbot. It should be: **present** (knows you, is here),
**useful** (does real things), **trustworthy** (private, honest), and **alive over
time** (learns, remembers, grows). Ten capability areas follow.

### 1. Memory — knows you across time ✅ strong
| Capability | State | Where |
| --- | --- | --- |
| Conversation memory (recent turns) | ✅ | `memory.py`, agent loop |
| Long-term sealed memory + recall | ✅ | `memory.py`, `life_memory.py` |
| A model of *you* (your patterns, people) | ✅ | `mental_model.py`, `contacts.py` |
| Her own life / sayings / stories (the twin) | ✅ | `life_story.py`, `remember.py` |
| Reconsolidation (reused memories strengthen) | ✅ | `memory.py` |
| Forgetting / decay / "that's stale" | 🟡 | reflections expire; general decay thin |

### 2. Voice & conversation — sounds like a person ✅ strong
| Neural voice (Kokoro), warm + consistent | ✅ | `voice/kokoro_tts.py` |
| Cloned voice of a loved one (XTTS) | ✅ | `voice_clone.py` |
| Speech-to-text (Whisper) | ✅ | `voice/stt.py` |
| Barge-in / interrupt | ✅ | `/api/speak/stop` |
| Voice adapts to how *you* speak | ✅ | `mirror.py` |
| Delivery shaped by feeling (pace/warmth) | ✅ | `feel.py` → cerebellum |
| Voice-load status shown to user | ✅ | `/api/voice/status` (just added) |

### 3. Emotional presence — feels, and meets your mood ✅ strong (rare)
| A real felt state (not sentiment tag) | ✅ | `feel.py` + brain engine (numpy limbic net) |
| Mood colours stance + voice | ✅ | `feel.py`, `mood.py` |
| Humor, gated to the moment | ✅ | temporal engine; `proactive.py` jokes |
| Crisis detection + gentle response | ✅ | `crisis.py` |
| Her own emotional honesty (never fakes) | ✅ | `life_story.py` doctrine |

### 4. Proactivity — reaches out, doesn't just wait ✅ (new)
| Timely reminders (NEED > WANT) | ✅ | `proactive.py` |
| Warm companion check-ins, spoken | ✅ | `proactive.py` (just added) |
| Context-aware restraint (hold back in a call) | ✅ | `presence.py` device sense |
| Learns *when* to reach out from your rhythms | 🟡 | rhythms exist; timing not yet learned |

### 5. Senses — aware of your world (on-device, opt-in) ✅ broad
| Camera: face/mood + "reading the room" | ✅ | `presence.py` (Vision/optical-flow) |
| Ambient sound types (never recorded) | ✅ | `presence.py` ear |
| Device ecosystem (meeting/video/music/work) | ✅ | `presence.py` device sense |
| Activity patterns (how you work) | ✅ | `activity.py` |
| Places / movement | ✅ | `places.py`, `importers/*location*` |
| Music taste | ✅ | `music.py` |
| Health / fitness signals | 🟡 | `health.py`, `watch.py` — thin, needs depth |
| Photos (on-device understanding) | 🟡 | `photos.py`, `portrait.py` — partial |

### 6. Getting things done — real actions, safely ✅ good, gated
| Email: triage + send (your account) | ✅ | `email_triage.py`, `email_send.py` |
| Calendar read + event awareness | ✅ | `calendar.py` |
| Contacts | ✅ | `contacts.py` |
| Screen/app control (named, confirmed) | ✅ | `control.py` |
| Skills framework (pluggable) | ✅ | `skills/*` |
| Booking / amenities | 🟡 | `skills/amenity_booking.py` — narrow |
| Open-ended task execution / agentic chains | 🟡 | council/think-routes exist; not deep |

### 7. Knowledge & reasoning — grounded, not hallucinated ✅ strong
| Local LLM reasoning (right-sized to the Mac) | ✅ | `providers.py`, `device_model.py` |
| RAG over your docs (cited, hybrid) | ✅ | `rag.py` |
| RAG over her convictions (trained reranker) | ✅ | `wisdom.py`, `rerank.py` (held-out proven) |
| Web research (fenced, opt-in) | ✅ | `net.py`, `skills/builtin.py` |
| Brain engine (anatomy-mapped, not just LLM) | ✅ | `brain.py` + human-brain-engine |
| Current affairs in conversation | 🟡 | `proactive.py` hook; needs a real news source |

### 8. Privacy & trust — the whole foundation ✅ exemplary
| On-device by default, sealed at rest | ✅ | `security.py`, `vault.py` (ChaCha20) |
| Keychain-bound keys | ✅ | `secrets_store.py` |
| One guarded egress doorway + allow-list | ✅ | `net.py`, `security.doctor()` |
| `security doctor` audits 6 fronts | ✅ | `security.py` |
| Every sense opt-in + pausable | ✅ | all sense modules |
| Honest about uncertainty (never launders a guess) | ✅ | `system_dna`, `life_story` |

### 9. Alive over time — learns & grows ✅ good
| Speech accommodation (learns your style) | ✅ | `mirror.py` |
| Tone dial (your control over delivery) | ✅ | `tone.py` |
| Trained models improve on measure | ✅ | `rerank.py`, limbic net |
| Rhythms / routines learned | ✅ | `rhythms.py` |
| Self-maintenance / health checks | ✅ | `maintenance.py`, `health.py` |
| Explicit "teach her" / feedback loop | 🟡 | `remember.py` interview; no in-chat "remember this" ergonomics |

### 10. Reach — with you everywhere ✅ designed, 🟡 shipping
| Mac app (menubar + web UI + voice) | ✅ | `voice/*`, `menubar.py` |
| iOS app (Anita) | ✅ | separate Xcode project |
| Multi-device private sync | 🟡 | `sync.py`, `twins.py` — designed, merge WIP |
| A visible "mind" view | ✅ | `viz.py` |

---

## The honest scorecard

**Strengths (top-tier, rare in personal AI):** on-device privacy with a real
security kernel; a brain that *feels* (not a sentiment label bolted on an LLM); a
loved-one's cloned voice; genuine proactivity with restraint; trained components
that improve on measure. Few "personal AI" apps have any of these; Vera has all.

**Thin spots worth depth (🟡):** health/fitness, photos understanding, learned
*timing* of proactivity, agentic multi-step task execution, in-chat "remember
this" ergonomics, real current-affairs source, and finishing multi-device sync.

**No glaring gaps (⬜):** the capability *surface* is remarkably complete. The work
now is **depth, polish, and reliability** on what exists — which matches Ankur's
steer: *"voice can improve with time but I need it to work… as good as possible."*

---

## Prioritized backlog (the next good updates)

Ordered by value × how-ready-the-foundation-is:

1. **Reliability pass on voice everywhere** — it must *always* speak (web + app).
   Status indicators done; next: a self-test on launch + a visible "her voice is
   X" everywhere. *Foundation: done. High value.*
2. **Learned proactivity timing** — she already reaches out; learn *when* you
   welcome it vs. not (from your responses + activity). *Foundation: `rhythms`,
   `presence`, `proactive`.*
3. **Real current-affairs source** — wire `proactive._current_affairs_line` to a
   genuine feed through `net.py` (opt-in), so "what people talk about" is real.
4. **In-chat "remember this about me"** — one-line teaching during conversation,
   sealed to `mental_model`/`wisdom`. Closes the feedback loop.
5. **Health/fitness depth** — `health.py` + `watch.py` from thin to a daily
   "how's your body" that folds into her care check-ins.
6. **Finish multi-device sync** — the merge/pairing in `sync.py`/`twins.py`, so
   she's genuinely the same companion on every screen.
7. **Agentic task chains** — deepen `council`/`think_routes` so "plan my week"
   becomes real multi-step action (behind the permission gate).
8. **Photos understanding** — on-device: "show me that day", face/place recall
   folded into memory.

Each stays on-device, opt-in, sealed, fail-soft, tested, and `security doctor`
SAFE — the bar everything here is held to.
