# iCloud sync — the same Vera on your Mac and iPhone, privately

Vera stays one companion across your devices by passing a **sealed bundle** of her
memory through **your own iCloud Drive** — no server of ours, nothing public.

## Why it's safe + private

- **Encrypted before it ever reaches iCloud.** iCloud only ever holds a locked
  file — Apple can't read it, and neither can anyone else. Only your devices, with
  your passphrase, can open it.
- **It's your iCloud, not ours.** The file lives in your own private iCloud Drive,
  tied to your Apple ID — the same account you're already signed into on both
  devices. There's no account of ours, nothing public.
- **Keys stay put.** Each device keeps its own key; only the memory travels, never
  the keys.
- **Syncing merges, never overwrites.** Both devices' changes survive; on a real
  clash, the newer one wins.
- **No iCloud? No problem.** If you're not signed in, Vera simply stays local.

<details><summary>Under the hood (for the curious)</summary>

The bundle is sealed with ChaCha20-Poly1305 via `vault.export_bundle`; it lives in
the `iCloud.com.sinhaankur.vera` container; `sync.merge_bundle` does the per-record
merge and refuses to move any device's key material.
</details>

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

## ⚠ Free Apple team vs. iCloud — the real tradeoff

A **free personal Apple team cannot sign the iCloud capability** ("Personal
development teams do not support the iCloud capability"). So on the free tier you
pick one:

- **Install free on your iPhone now** → strip the `entitlements:` block + the
  `NSUbiquitousContainers` key from `ios/project.yml`, regenerate, build. The app
  installs and runs **fully**; `sync_icloud` is simply a no-op until a device has
  the entitlement. (This is how the app was side-loaded onto the iPhone.)
- **iCloud sync on device** → needs the **paid Apple Developer Program** ($99/yr).
  Keep the entitlement as committed and it works.

The sync CODE is built + tested either way — it just activates when a build carries
the entitlement.

### The exact commands used to side-load (free team, no iCloud)

```bash
cd core && ./build-xcframework.sh          # build the Rust core
cd ../ios
# (strip the entitlements + NSUbiquitousContainers from project.yml for free team)
xcodegen generate
xcodebuild -project Anita.xcodeproj -scheme Anita \
  -destination "platform=iOS,id=<your-iphone-udid>" -configuration Debug \
  -allowProvisioningUpdates DEVELOPMENT_TEAM=<team> CODE_SIGN_STYLE=Automatic build
xcrun devicectl device install app --device <your-iphone-udid> \
  ~/Library/Developer/Xcode/DerivedData/Anita-*/Build/Products/Debug-iphoneos/Anita.app
```

First launch on the phone: **Settings → General → VPN & Device Management → trust
your developer profile**, then tap Vera.
