# Notarizing Vera — OPTIONAL, for later

Vera ships **signed but not notarized**, and that is a deliberate, fine choice —
not a gap. The only practical difference is a one-time **right-click → Open** on
first launch (macOS: *"Apple cannot check it for malicious software"*). After
that one click, it opens normally forever. Many respected open-source Mac apps
ship exactly this way; the DMG and the download page explain the step warmly so
it never feels sketchy.

**Notarizing would remove even that one click** — but it requires an **Apple
Developer Program membership ($99/year)**, which isn't worth it for a free,
open-source project until there's real demand. This doc is here so that *if and
when* that day comes, it's a short, documented step — not a blocker, and nothing
to feel is "missing" in the meantime.

---

## One-time setup (after joining the Developer Program)

1. **Get a Developer ID Application certificate** (not the "Apple Development"
   one the build already uses — notarization needs *Developer ID*):
   - Xcode → Settings → Accounts → your team → *Manage Certificates* → `+` →
     **Developer ID Application**. Or create it at developer.apple.com.

2. **Create an app-specific password** for notarytool at appleid.apple.com →
   Sign-In & Security → App-Specific Passwords.

3. **Store the credentials once** (keychain profile named `vera-notary`):
   ```bash
   xcrun notarytool store-credentials vera-notary \
     --apple-id "you@example.com" \
     --team-id "DS8C97S284" \
     --password "the-app-specific-password"
   ```

---

## Per-release (what the build does once wired)

The steps, in order — `build-app.sh` already does step 1 (signing); steps 2–4
are the notarization add-on:

1. **Sign** with the Developer ID cert + hardened runtime (`--options runtime`).
   *(build-app.sh already signs; point `SIGN_ID` at the Developer ID cert.)*
2. **Zip** the app for submission:
   ```bash
   ditto -c -k --keepParent "Vera.app" "Vera.zip"
   ```
3. **Notarize** (uploads to Apple, waits for the ticket — usually < 5 min):
   ```bash
   xcrun notarytool submit "Vera.zip" --keychain-profile vera-notary --wait
   ```
4. **Staple** the ticket onto the app so it verifies offline:
   ```bash
   xcrun stapler staple "Vera.app"
   ```
5. **Re-zip the stapled app** and attach THAT to the GitHub release.

Verify it worked:
```bash
spctl -a -vvv -t install "Vera.app"     # → "accepted … source=Notarized Developer ID"
```

---

## Until then

The free fixes already shipped make this as painless as possible without
notarization:
- the one-line installer auto-installs everything (Homebrew, git, Python, Ollama,
  the right-sized model, the voice, the brain service);
- the download page + install script tell the user clearly to **right-click →
  Open** the first time, and *why* (open-source, ad-hoc trusted, nothing hidden).

So a user **can** install it today — they just click through one Gatekeeper
prompt. Notarizing removes even that.
