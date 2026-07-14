#!/usr/bin/env bash
# Build "Vera.app" -- a real, double-clickable macOS app bundle.
#
#   ./build-app.sh            # builds and places Vera.app in this folder
#   open "Vera.app"     # launch it
#
# The bundle includes the Info.plist permission strings macOS requires for the
# microphone + speech recognition (without them the app crashes on first listen).

set -euo pipefail
cd "$(dirname "$0")"

APP="Vera.app"
BIN_NAME="Vera"

echo "[1/4] Compiling (release, cross-module optimized)..."
T0=$(date +%s)
swift build -c release -Xswiftc -cross-module-optimization

BIN_PATH="$(swift build -c release --show-bin-path)/$BIN_NAME"
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

# App icon (Anita's orb). Generate it if missing.
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
  <key>CFBundleVersion</key>         <string>0.2.2</string>
  <key>CFBundleShortVersionString</key> <string>0.2.2</string>
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
  <string>Anita listens to your voice so you can talk with her - and, only when you turn on "Hear the room", reads ambient sound types (music, typing) on-device. Audio stays on this machine and is never recorded.</string>
  <key>NSSpeechRecognitionUsageDescription</key>
  <string>Anita transcribes your speech on-device to understand you.</string>
  <key>NSCameraUsageDescription</key>
  <string>Only when you turn on "See me": she reads face cues on-device - present, calm vs animated, a nod, a smile, a knitted brow. No video is stored or sent anywhere.</string>
  <key>NSPhotoLibraryUsageDescription</key>
  <string>Only when you turn on "Read my Photos": she reads album names and dates - metadata only, never the photos themselves - to learn life events like birthdays and anniversaries. Nothing is uploaded or copied.</string>
</dict>
</plist>
PLIST

echo "[4/5] Code-signing (ad-hoc)..."
codesign --force --deep --sign - "$APP" 2>/dev/null || echo "  (codesign skipped -- app still runs locally)"

# ONE install per device: the app lives in /Applications and nowhere else.
# The staging bundle is removed so Spotlight/Launchpad never see two copies.
echo "[5/5] Installing to /Applications..."
rm -rf "/Applications/$APP"
cp -R "$APP" "/Applications/$APP"
rm -rf "$APP"

echo ""
echo "Installed: /Applications/$APP"
echo "  Launch it:   open \"/Applications/$APP\""
echo "  First launch asks for Microphone + Speech Recognition -- allow both."
