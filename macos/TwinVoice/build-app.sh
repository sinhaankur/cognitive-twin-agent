#!/usr/bin/env bash
# Build "Twin Voice.app" -- a real, double-clickable macOS app bundle.
#
#   ./build-app.sh            # builds and places Twin Voice.app in this folder
#   open "Twin Voice.app"     # launch it
#
# The bundle includes the Info.plist permission strings macOS requires for the
# microphone + speech recognition (without them the app crashes on first listen).

set -euo pipefail
cd "$(dirname "$0")"

APP="Twin Voice.app"
BIN_NAME="TwinVoice"

echo "[1/4] Compiling (release)..."
swift build -c release

BIN_PATH="$(swift build -c release --show-bin-path)/$BIN_NAME"
if [ ! -f "$BIN_PATH" ]; then
  echo "build failed: $BIN_PATH not found" >&2
  exit 1
fi

echo "[2/4] Assembling $APP..."
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN_PATH" "$APP/Contents/MacOS/$BIN_NAME"

echo "[3/4] Writing Info.plist..."
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>            <string>Twin Voice</string>
  <key>CFBundleDisplayName</key>     <string>Twin Voice</string>
  <key>CFBundleIdentifier</key>      <string>com.sinhaankur.twinvoice</string>
  <key>CFBundleVersion</key>         <string>0.1.0</string>
  <key>CFBundleShortVersionString</key> <string>0.1.0</string>
  <key>CFBundlePackageType</key>     <string>APPL</string>
  <key>CFBundleExecutable</key>      <string>TwinVoice</string>
  <key>LSMinimumSystemVersion</key>  <string>13.0</string>
  <key>NSHighResolutionCapable</key> <true/>
  <key>LSApplicationCategoryType</key> <string>public.app-category.productivity</string>
  <!-- Permission prompts (required or the app crashes on first use) -->
  <key>NSMicrophoneUsageDescription</key>
  <string>Twin Voice listens to your voice so you can talk to your local AI - audio stays on this machine.</string>
  <key>NSSpeechRecognitionUsageDescription</key>
  <string>Twin Voice transcribes your speech on-device to send your words to the local agent.</string>
</dict>
</plist>
PLIST

echo "[4/4] Code-signing (ad-hoc)..."
codesign --force --deep --sign - "$APP" 2>/dev/null || echo "  (codesign skipped -- app still runs locally)"

echo ""
echo "Built: $(pwd)/$APP"
echo "  Launch it:   open \"$APP\""
echo "  First launch asks for Microphone + Speech Recognition -- allow both."
