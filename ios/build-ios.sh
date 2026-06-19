#!/usr/bin/env bash
# Build the iOS Anita app. One command: regenerate the project, build the Rust
# core's xcframework, and compile for the simulator.
set -euo pipefail
cd "$(dirname "$0")"
echo "[1/3] Building Rust core xcframework..."
( cd ../core && ./build-xcframework.sh >/dev/null )
echo "[2/3] Generating Xcode project..."
xcodegen generate
echo "[3/3] Building for iOS Simulator..."
SIM=$(xcrun simctl list devices available | grep -iE "iPhone 1[567]" | head -1 | grep -oE "\([A-F0-9-]{36}\)" | tr -d '()')
xcodebuild -project Anita.xcodeproj -scheme Anita -destination "platform=iOS Simulator,id=$SIM" -configuration Debug build | tail -3
echo "Done. Open Anita.xcodeproj in Xcode to run on your device, or:"
echo "  xcrun simctl install $SIM <path to Anita.app> && xcrun simctl launch $SIM com.sinhaankur.anita"
