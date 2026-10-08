#!/usr/bin/env bash
# make-dmg.sh — package Vera.app into a double-clickable .dmg for release.
#
#   ./scripts/make-dmg.sh [path/to/Vera.app]
#
# Produces Vera.dmg: a disk image the user double-clicks, then drags Vera into
# the Applications folder — the familiar, no-Terminal macOS install gesture. This
# is the closest to "pure double-click" without notarization; the only remaining
# prompt is Gatekeeper's one-time "right-click → Open", which notarization
# removes entirely (see docs/NOTARIZATION.md).
set -uo pipefail

APP="${1:-/Applications/Vera.app}"
[ -d "$APP" ] || APP="$(cd "$(dirname "$0")/.." && pwd)/macos/Vera/Vera.app"
if [ ! -d "$APP" ]; then
  echo "Vera.app not found. Build it first: (cd macos/Vera && ./build-app.sh)"
  exit 1
fi

OUT_DIR="$(cd "$(dirname "$0")/.." && pwd)/dist"
mkdir -p "$OUT_DIR"
DMG="$OUT_DIR/Vera.dmg"
STAGE="$(mktemp -d)/Vera"
mkdir -p "$STAGE"

echo "-> staging the disk image..."
cp -R "$APP" "$STAGE/"
# the drag-to-install gesture: an Applications symlink right next to the app
ln -s /Applications "$STAGE/Applications"

# a short, friendly first-open note (so the one Gatekeeper step isn't a surprise)
cat > "$STAGE/START HERE.txt" <<'TXT'
  Welcome to Vera — a private, on-device AI companion.
  ─────────────────────────────────────────────────────

  TWO STEPS. That's it.

  STEP 1 — Install
     Drag   Vera   onto the   Applications   folder (it's right here →).

  STEP 2 — Open it (the first time only)
     Go to your Applications folder.
     RIGHT-CLICK  Vera  →  choose  Open  →  click  Open.

     (Normal double-click won't work the FIRST time — you must right-click
      → Open once. This is normal for free, open-source apps: macOS just
      wants you to confirm. Nothing is hidden, nothing is uploaded. Every
      time after this, a normal double-click works.)

  That's all. Vera sets up the rest herself, right on your Mac.
  Give her a few minutes on first launch, then click the glowing orb to talk.
TXT

echo "-> building $DMG..."
rm -f "$DMG"
hdiutil create -volname "Vera" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null \
  && echo "OK: created $DMG" \
  || { echo "hdiutil failed"; exit 1; }

echo
echo "Attach THIS .dmg to the GitHub release. The user double-clicks it and drags"
echo "Vera to Applications — no Terminal. (Notarize to remove the one Gatekeeper"
echo "prompt — see docs/NOTARIZATION.md.)"
