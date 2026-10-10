# Installing Vera

Vera is an **on-device** companion — she runs on *your* machine, and nothing you
say leaves it. This guide gets her onto your Mac, and (if you want) your iPhone.

> **Where this is today:** Vera is a personal project, built and polished for one
> person first. It works and it's real, but it's not a one-tap App Store download
> yet — setup takes a few minutes and, on iPhone, a free Apple developer account.
> If you're not technical, the **Mac** path below is the easy one.

---

## Mac — the easy path (one command)

1. Open **Terminal** (press ⌘-Space, type "Terminal", hit return).
2. Paste this and press return:

   ```bash
   curl -fsSL https://raw.githubusercontent.com/sinhaankur/cognitive-twin-agent/main/scripts/install-vera.sh | bash
   ```

   It installs everything she needs (the local model engine, her brain, her
   voice) — explaining each step. It only ever installs; it never uploads.

3. When it finishes, download **Vera.app** from the
   [latest release](https://github.com/sinhaankur/cognitive-twin-agent/releases/latest),
   move it to **Applications**, and the first time **right-click → Open** (she's
   free and open-source, not App-Store-signed, so macOS asks once).

That's it — click the orb and talk to her.

---

## iPhone — for now, a developer build

The iPhone app runs the same companion as a movement/places-aware subset. Putting
it on a phone today needs a Mac with **Xcode** and a **free Apple ID** (no paid
account needed for the basic app — see the note on iCloud below).

1. On the Mac, get the code:
   ```bash
   git clone https://github.com/sinhaankur/cognitive-twin-agent
   cd cognitive-twin-agent/core && ./build-xcframework.sh     # builds the core
   cd ../ios && xcodegen generate && open Anita.xcodeproj
   ```
2. In Xcode → the **Anita** target → **Signing & Capabilities**: pick your Apple
   ID as the Team (the free personal one is fine).
3. Plug in your iPhone, select it as the destination, press **Run**.
4. First launch on the phone: **Settings → General → VPN & Device Management →
   trust your developer profile**, then open Vera.
5. **Connect her to her brain.** A phone can't run the model; it reaches the one
   on your Mac, privately over Tailscale. See **[IPHONE-SETUP.md](./IPHONE-SETUP.md)**.

**iCloud sync note:** a *free* Apple account can't use the iCloud capability, so a
free build installs **without** cross-device sync (the app still works fully). For
the "same Vera on Mac + iPhone, through your iCloud" sync, you need a paid Apple
Developer account — see [ICLOUD-SYNC.md](./ICLOUD-SYNC.md).

---

## What she needs to run well

- A **Mac** (Apple Silicon is best — her voice + a local model run fast on it).
- **Ollama** (the local model engine) — the Mac installer sets this up for you.
- Disk for one small local model (the installer picks the right size for your Mac).

Everything is on-device and private by design. If you hit a snag, the
[README](../README.md) has the deeper detail.
