#!/usr/bin/env bash
# Build CognitiveTwinCore.xcframework — the Rust core packaged for Apple platforms
# (iOS device + iOS simulator). Drop the result into an Xcode app and call the
# ctwin_* C functions from Swift.
#
#   ./build-xcframework.sh
#
# Output: core/CognitiveTwinCore.xcframework

set -euo pipefail
cd "$(dirname "$0")"

LIB=libcognitive_twin_core.a
OUT=CognitiveTwinCore.xcframework
HEADERS=include

echo "[1/3] Building Rust static libs for Apple targets..."
cargo build --release --target aarch64-apple-ios
cargo build --release --target aarch64-apple-ios-sim

DEVICE="target/aarch64-apple-ios/release/$LIB"
SIM="target/aarch64-apple-ios-sim/release/$LIB"

for f in "$DEVICE" "$SIM"; do
  [ -f "$f" ] || { echo "missing $f" >&2; exit 1; }
done

echo "[2/3] Assembling $OUT..."
rm -rf "$OUT"
xcodebuild -create-xcframework \
  -library "$DEVICE" -headers "$HEADERS" \
  -library "$SIM"    -headers "$HEADERS" \
  -output "$OUT"

echo "[3/3] Done."
echo "Built: $(pwd)/$OUT"
echo "  Add it to your Xcode app (Frameworks), import via a bridging header:"
echo "    #include \"cognitive_twin_core.h\""
