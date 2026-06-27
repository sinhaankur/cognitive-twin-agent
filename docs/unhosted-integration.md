# Cognitive Twin × Unhosted — Integration Design

Merge Cognitive Twin into [Unhosted](https://github.com/unhosted-ai/unhosted-core)
as a capability a user **enables** — not a separate app pointed at it.

- **Unhosted** = the always-on local inference cluster (Rust, wraps `llama.cpp`,
  pools device VRAM, daemon + web UI on `:7777`).
- **Cognitive Twin** = the optional assistant layer a user turns on *if they want
  an AI assistant*: a persona, private memory, and a loved one's cloned voice.

> One brain (Unhosted), one optional soul (the Twin). Both stay on hardware you own.

## Role split

| Concern | Owner |
|---|---|
| Model inference, VRAM pooling, trust radius (local/trusted/public) | **Unhosted** |
| OpenAI-compatible endpoint at `:7777/v1` | **Unhosted** |
| Persona, private memory, model routing policy, agent loop | **Twin** |
| Voice clone (24kHz XTTS, on-device) | **Twin** (Python-bridged) |
| The "Cognitive Twin" enable toggle in the web UI | **Unhosted UI → Twin crate** |

## The seam (verified)

The integration point already exists and is confirmed working against a live
daemon:

```
GET http://127.0.0.1:7777/v1/models  → HTTP 200, OpenAI shape
chat → POST http://127.0.0.1:7777/v1/chat/completions
```

Cognitive Twin's `cognitive_twin/llm/providers.py` already:
- auto-detects the daemon (`unhosted_base_url()` → `:7777/v1`),
- labels its models `unhosted/<name>`,
- builds an `OpenAIClient` to reason through it.

A real reasoning turn through Unhosted was verified end-to-end.

### Integration gotchas found while verifying

1. **Keyless auth.** Unhosted's `:7777/v1` returns `401` for a bogus bearer token.
   The client must send **no** `Authorization` header unless a real key is set.
   (Fixed in `OpenAIClient`.)
2. **Backend ambiguity.** When Ollama (`:11434`) and Unhosted (`:7777`) both serve
   the *same* model names, untagged ids route to whichever de-dupes first. The
   crate must disambiguate by **provider tag**, not bare name.

## Integration shape — native Rust crate

Target: a new crate `crates/unhosted-twin` inside `unhosted-core`. The voice clone
and the existing agent loop are **Python**; they are *bridged*, not rewritten, in
the first phase.

```
unhosted-core/
  crates/
    unhosted-core/         (existing)
    unhosted-twin/         (NEW)
      src/
        lib.rs             capability registration + enable/disable
        persona.rs         persona store (port of persona.py: load/save/to_prompt)
        memory.rs          private memory (owner-only, local)
        router.rs          model-routing policy (port of agent/router.py)
        bridge.rs          spawn/supervise the Python voice + agent worker
        api.rs             web-UI endpoints: status, enable, persona, speak
      python/              bundled Twin worker (voice_clone, agent loop)
```

### Phasing (lowest risk first)

1. **Phase 0 — wire, don't port.** Crate is a thin supervisor: it exposes an
   enable toggle and launches the existing Python Twin, pointing its
   `CTWIN_OPENAI_BASE` at the in-process Unhosted endpoint. Ships the merge with
   minimal Rust.
2. **Phase 1 — port the cheap, pure logic to Rust.** persona, memory, router
   (no ML deps). The voice engine stays Python over `bridge.rs`.
3. **Phase 2 — first-class UI + trust radius.** Enable toggle, persona editor, and
   voice setup in the `:7777` web UI; respect Unhosted's local/trusted/public modes
   (the Twin's private memory must never leave the local trust radius).

## Voice path

XTTS is Python/ML and platform-specific; do **not** rewrite in Rust. `bridge.rs`
keeps a warm Python worker (the existing `_xtts_say.py --serve` pattern) and the
crate sends it text → gets back a WAV path. Reference prep (24kHz gentle clean)
and synthesis tuning already live in the Twin and carry over unchanged.

## Privacy invariants (must hold after merge)

- Persona, memory, and the voice sample stay **owner-only, on-device**.
- The Twin's private memory never crosses Unhosted's **local** trust boundary into
  trusted/public modes.
- Camera/mic/screen remain **off by default**, explicit opt-in (see the deferred
  permissions work).

## Open questions

- Does `unhosted-core` expose a capability/module registry, or is the toggle a
  direct edit to its crates + web UI? (No documented extension API today.)
- Bundle the Python Twin worker with Unhosted, or detect an existing install?
- Where does persona/voice setup live — Unhosted's web UI, or a deep link to the
  Twin's own setup?

## Status

- [x] Verify the `:7777/v1` seam against a real daemon
- [x] Fix keyless-auth 401 in `OpenAIClient`
- [ ] Confirm Unhosted's extension/module story (crate vs. registry)
- [ ] Scaffold `crates/unhosted-twin` (Phase 0 supervisor)
- [ ] Web-UI enable toggle
- [ ] Bridge the voice worker
