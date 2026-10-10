#!/usr/bin/env bash
# Build "Vera.app" -- a real, double-clickable macOS app bundle.
#
#   ./build-app.sh            # builds and places Vera.app in this folder
#   ./build-app.sh --universal  # Apple Silicon + Intel in one bundle (for sharing)
#   open "Vera.app"     # launch it
#
# The bundle includes the Info.plist permission strings macOS requires for the
# microphone + speech recognition (without them the app crashes on first listen).

set -euo pipefail
cd "$(dirname "$0")"

APP="Vera.app"
BIN_NAME="Vera"

# Native arch by default (your own machine); --universal adds Intel so the
# bundle runs on any Mac someone drags it onto.
ARCH_FLAGS=""
[ "${1:-}" = "--universal" ] && ARCH_FLAGS="--arch arm64 --arch x86_64"

echo "[1/4] Compiling (release, cross-module optimized${ARCH_FLAGS:+, universal})..."
T0=$(date +%s)
swift build -c release $ARCH_FLAGS -Xswiftc -cross-module-optimization

BIN_PATH="$(swift build -c release $ARCH_FLAGS --show-bin-path)/$BIN_NAME"
if [ ! -f "$BIN_PATH" ]; then
  echo "build failed: $BIN_PATH not found" >&2
  exit 1
fi
echo "  ($(($(date +%s) - T0))s)"

echo "[2/4] Assembling $APP..."
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN_PATH" "$APP/Contents/MacOS/$BIN_NAME"
# strip debug symbols from the bundled copy (the .build one keeps them)
strip -rSTx "$APP/Contents/MacOS/$BIN_NAME" 2>/dev/null || true
echo "  binary: $(du -h "$APP/Contents/MacOS/$BIN_NAME" | cut -f1) (was $(du -h "$BIN_PATH" | cut -f1))"

# App icon (Vera's orb). Generate it if missing.
if [ ! -f AppIcon.icns ]; then
  echo "  (generating AppIcon.icns)"; python3 make-icon.py >/dev/null 2>&1 || true
fi
[ -f AppIcon.icns ] && cp AppIcon.icns "$APP/Contents/Resources/AppIcon.icns"

echo "[3/4] Writing Info.plist..."
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>            <string>Vera</string>
  <key>CFBundleDisplayName</key>     <string>Vera</string>
  <!-- identifier kept as 'anita' on purpose: changing it would reset the
       mic/speech/accessibility permissions the user already granted -->
  <key>CFBundleIdentifier</key>      <string>com.sinhaankur.anita</string>
  <key>CFBundleVersion</key>         <string>0.3.1</string>
  <key>CFBundleShortVersionString</key> <string>0.3.1</string>
  <key>CFBundlePackageType</key>     <string>APPL</string>
  <key>CFBundleExecutable</key>      <string>Vera</string>
  <key>CFBundleIconFile</key>        <string>AppIcon</string>
  <key>CFBundleIconName</key>        <string>AppIcon</string>
  <key>LSMinimumSystemVersion</key>  <string>13.0</string>
  <key>NSHighResolutionCapable</key> <true/>
  <!-- one of her per device: never two instances of the same bundle -->
  <key>LSMultipleInstancesProhibited</key> <true/>
  <key>LSApplicationCategoryType</key> <string>public.app-category.productivity</string>
  <!-- Menu-bar / floating app: no Dock icon -->
  <key>LSUIElement</key>            <true/>
  <!-- Permission prompts (required or the app crashes on first use) -->
  <key>NSMicrophoneUsageDescription</key>
  <string>Listens to your voice so you can talk - and, only when you turn on "Hear the room", reads ambient sound types (music, typing) on-device. Audio stays on this machine and is never recorded.</string>
  <key>NSSpeechRecognitionUsageDescription</key>
  <string>Transcribes your speech on-device to understand you.</string>
  <key>NSCameraUsageDescription</key>
  <string>Only when you turn on "See me": reads face cues on-device - present, calm vs animated, a nod, a smile, a knitted brow. No video is stored or sent anywhere.</string>
  <key>NSPhotoLibraryUsageDescription</key>
  <string>Only when you turn on "Read my Photos": reads album names and dates - metadata only, never the photos themselves - to learn life events like birthdays and anniversaries. Nothing is uploaded or copied.</string>
</dict>
</plist>
PLIST

echo "[4/5] Code-signing (stable identity so mic + speech grants STICK)..."
# Entitlements so the microphone + speech recognition work reliably. Critically,
# we sign with a STABLE identity (your Apple Development cert) when one exists,
# NOT ad-hoc: an ad-hoc signature changes every rebuild, so macOS treats each
# build as a new app and REVOKES the mic/speech grant — the root cause of "I
# grant access, still it lacks / loops into error". A real cert keeps the grant.
ENT="$(mktemp -t vera-entitlements).plist"
cat > "$ENT" <<'ENTITLEMENTS'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>com.apple.security.device.audio-input</key><true/>
  <key>com.apple.security.device.microphone</key><true/>
  <key>com.apple.security.personal-information.speech-recognition</key><true/>
</dict>
</plist>
ENTITLEMENTS
# Prefer a real "Apple Development" identity (stable, trusted by TCC). Fall back
# to ad-hoc only if none is installed.
SIGN_ID="$(security find-identity -v -p codesigning 2>/dev/null \
  | grep -E 'Apple Development|Developer ID Application' | head -1 \
  | sed -E 's/.*\) ([A-F0-9]{40}) .*/\1/')"
if [ -n "$SIGN_ID" ]; then
  echo "  using identity: $SIGN_ID"
  codesign --force --deep --options runtime --sign "$SIGN_ID" \
    --entitlements "$ENT" "$APP" \
    && echo "  signed with your Apple Development identity (mic/speech grants persist)" \
    || { echo "  (identity sign failed — falling back to ad-hoc)"; \
         codesign --force --deep --sign - --entitlements "$ENT" "$APP" 2>/dev/null; }
else
  echo "  no Apple Development identity found — ad-hoc (mic may need re-granting each build)"
  codesign --force --deep --sign - --entitlements "$ENT" "$APP" 2>/dev/null \
    || echo "  (codesign skipped -- app still runs locally)"
fi
rm -f "$ENT"

# ONE install per device: the app lives in /Applications and nowhere else.
# The staging bundle is removed so Spotlight/Launchpad never see two copies.
echo "[5/5] Installing to /Applications..."
# Quit any running copy FIRST — otherwise you keep using the OLD build after a
# rebuild (which looks like "my fix didn't take" + permissions seem reset). We
# relaunch the fresh build below so you're always on the latest.
WAS_RUNNING=0
if pgrep -f "/Applications/$APP/Contents/MacOS/$BIN_NAME" >/dev/null 2>&1; then
  WAS_RUNNING=1
  osascript -e "quit app \"$BIN_NAME\"" 2>/dev/null || true
  sleep 1
  pkill -f "/Applications/$APP/Contents/MacOS/$BIN_NAME" 2>/dev/null || true
  sleep 1
fi
rm -rf "/Applications/$APP"
cp -R "$APP" "/Applications/$APP"
rm -rf "$APP"
# relaunch the fresh build if one was running (so you never stay on a stale copy)
if [ "$WAS_RUNNING" = "1" ]; then
  echo "  relaunching the fresh build…"
  open "/Applications/$APP" 2>/dev/null || true
fi

# ---- activate the brain: make sure the LLM is actually there ----------------
# A good install leaves Vera ready to think, not just installed. Check Ollama is
# running and at least one chat model is pulled; start / pull if needed so the
# first launch isn't "LLM missing". Entirely local; skipped gracefully if Ollama
# isn't installed (the app still runs, just asks the user to set a model up).
echo "[activate] Checking the local LLM (Ollama)..."
if command -v ollama >/dev/null 2>&1; then
  if ! curl -s -m 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "  Ollama not running — starting it..."
    (ollama serve >/dev/null 2>&1 &) ; sleep 4
  fi
  MODELS="$(curl -s -m 5 http://127.0.0.1:11434/api/tags 2>/dev/null)"
  if ! echo "$MODELS" | grep -qiE 'qwen|llama|mistral|empathia'; then
    echo "  No chat model found — pulling a small one (qwen2.5:3b)..."
    ollama pull qwen2.5:3b || echo "  (pull failed — pull a model later: ollama pull qwen2.5:3b)"
  else
    echo "  LLM ready."
  fi
else
  echo "  Ollama isn't installed. Vera thinks on a local model via Ollama."
  echo "  Install it from https://ollama.com, then: ollama pull qwen2.5:3b"
fi

echo ""
echo "============================================================"
echo " Vera installed: /Applications/$APP"
echo "============================================================"
echo "  1. Launch:   open \"/Applications/$APP\""
echo "  2. First launch asks for Microphone + Speech Recognition — allow BOTH."
echo "     (Speech Recognition is separate from Microphone — grant it too, or"
echo "      the mic can't transcribe.)"
echo "  3. She speaks in her Kokoro neural voice by default; toggle in Settings."
echo "  4. If the mic button does nothing, open System Settings ▸ Privacy &"
echo "     Security ▸ Speech Recognition and enable Vera."
echo "============================================================"
