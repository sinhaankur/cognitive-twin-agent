# cognitive-twin-core (Rust)

The **portable core** of the Cognitive Twin — one codebase that runs on every
device. Pure, platform-agnostic logic shared by all front ends:

- **persona** — who the twin is (likes/dislikes/values → system-prompt block)
- **memory** — recurring-topic patterns from past prompts (private personalization)
- **router** — policy-driven local-model selection (complexity + risk + device)
- `build_system_prompt` — assembles base + persona + memory the way the agent does

Platform shells provide the I/O (HTTP to the model, files, audio); this crate is
the brain logic, kept identical everywhere. It mirrors the Python
`cognitive_twin` package so the two stay in parity during the port.

## Why Rust

> "Rust code would work on all the devices."

One core compiles to **macOS, iOS, iPadOS, Windows, Linux, Android, and WASM
(browser)**. Verified building today:

```bash
cargo test                                            # native + unit tests
cargo build --release --target aarch64-apple-ios      # iPhone/iPad
cargo build --release --target aarch64-apple-ios-sim  # iOS Simulator
cargo build --release --target wasm32-unknown-unknown # web
```

The iOS builds produce `libcognitive_twin_core.a` with a C ABI
(`ctwin_persona_prompt`, `ctwin_route`, `ctwin_system_prompt`, `ctwin_string_free`)
that a Swift/SwiftUI app links directly — the path to a native iOS Twin.

## Consuming it

- **Swift (iOS/macOS):** link the static lib + call the `ctwin_*` C functions
  (a bridging header / module map). Strings cross as UTF-8; free returns with
  `ctwin_string_free`.
- **Rust / WASM:** use the modules directly (`Persona`, `Router`, `summary_for_prompt`).

## Status

Core logic + FFI in place and cross-compiling to all targets. Next: the model
HTTP client (per-platform), then wire a native iOS shell onto this core.
