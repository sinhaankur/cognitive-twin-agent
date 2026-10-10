# iCloud sync — the same Vera on your Mac and iPhone, privately

Vera stays one companion across your devices by passing a **sealed bundle** of her
memory through **your own iCloud Drive** — no server of ours, nothing public.

## Why it's safe + private

- The bundle is **encrypted before it ever touches iCloud** (`vault.export_bundle`,
  ChaCha20-Poly1305 under a passphrase you set). iCloud only holds ciphertext —
  Apple can't read it, nor can anyone else.
- It lives in a **private iCloud Drive container scoped to your Apple ID**
  (`iCloud.com.sinhaankur.vera`). The trust is your iCloud account: the same person
  Apple already authenticates on both devices. Vera doesn't invent its own login —
  it inherits that.
- **Per-device keys never move.** The bundle carries memory, not a device's sealing
  key (`sync.merge_bundle` refuses key material). Each device keeps its own
  Keychain key; the shared passphrase unlocks the bundle.
- Pulling is a **merge, never an overwrite** — both devices' edits survive; newest
  wins on a true conflict.
- No iCloud / not signed in → every call is a clean **no-op**. Vera stays local.

## How it works

```
each device, on a timer or on demand:
  push()  → export a fresh SEALED bundle → <device>.ctwin in your iCloud Drive
  pull()  → for every OTHER device's bundle in iCloud → merge it in (no loss)
```

## Turn it on (one-time, on BOTH devices)

Set the **same** sync passphrase on each device so each can unseal the shared
bundle:

```bash
# on the Mac
python3 -m cognitive_twin.sync_icloud set "your-shared-passphrase"
python3 -m cognitive_twin.sync_icloud status     # should say "ready"
```

On the iPhone the app sets it in Settings (same passphrase). Then:

```bash
python3 -m cognitive_twin.sync_icloud sync        # pull others, then push ours
```

## Installing the iPhone app (your step — needs Xcode)

The Python/sync side is built and tested; putting the app on your iPhone is an
interactive Xcode build (I can't do it headless). Steps:

1. **Generate the project** (the iCloud entitlement is already in the spec):
   ```bash
   cd ios && xcodegen generate && open Anita.xcodeproj
   ```
2. In Xcode → the **Anita** target → **Signing & Capabilities**:
   - Team: your free personal team (no paid Developer Program needed for side-load).
   - Confirm **iCloud → iCloud Documents** is on, container
     `iCloud.com.sinhaankur.vera` checked. (The entitlement file is already wired.)
3. Wake your iPhone and **plug it in / pair it** — it currently shows as *Offline*
   to Xcode. Trust the Mac on the phone if prompted.
4. Select your iPhone as the run destination, press **Run**. First launch:
   **Settings → General → VPN & Device Management → trust your developer profile.**
5. On the iPhone, make sure **iCloud Drive is on** for Vera (Settings → your name →
   iCloud → see Vera), and set the **same sync passphrase** in the app.

Once both devices have the app, iCloud on, and the same passphrase, they stay in
step — health, activity, emotion, memory, all of it, privately through your iCloud.
