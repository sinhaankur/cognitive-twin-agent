# Twin Voice — iOS

The Cognitive Twin on iPhone/iPad, powered by the **shared Rust core**
(`core/`). The agent brain — persona, memory, routing, prompt assembly, and the
model call — is the same Rust code that runs on macOS and the web; iOS just adds
a SwiftUI shell over it.

## What's here

- `Sources/TwinCore.swift` — Swift bridge over the Rust C ABI (`ctwin_*`).
- `Sources/TwinVoiceApp.swift` — app entry + state (`TwinModel`).
- `Sources/TwinView.swift` — the Siri screen + persona editor.
- `Sources/SiriOrb.swift` — the multicolor Siri orb (shared with macOS, pure SwiftUI).

## Build (Xcode)

The Rust core builds into an `.xcframework`; assembling the final `.app` is an
Xcode step (project/signing live in Xcode's GUI):

1. **Build the core for Apple platforms:**
   ```bash
   cd ../core && ./build-xcframework.sh
   ```
   → produces `core/CognitiveTwinCore.xcframework` (iOS device + simulator).

2. **In Xcode:** create an iOS App target, add the four files in `Sources/`, then:
   - Drag `CognitiveTwinCore.xcframework` into the target (Frameworks, Libraries,
     and Embedded Content).
   - Add a **bridging header** containing:
     ```c
     #include "cognitive_twin_core.h"
     ```
   - Set **Info.plist** keys: `NSMicrophoneUsageDescription`,
     `NSSpeechRecognitionUsageDescription` (for the voice add-on).

3. Run on a device or simulator.

## Model host

Phones don't run Ollama locally, so point the twin at a machine that does (your
Mac or home server) — set the host in `TwinModel` / a setting. The privacy story
holds when that machine is yours (this is exactly the Unhosted "trusted device"
idea). On-device Apple Intelligence can be wired as an alternative backend later.

## Status

Sources + the Swift↔Rust bridge are in place and the core's xcframework builds.
The Xcode project wrapper is the remaining manual step (GUI-only). The Rust core
is verified end-to-end (talks to a live model), so the brain is proven; this shell
calls the same `ctwin_ask`.
