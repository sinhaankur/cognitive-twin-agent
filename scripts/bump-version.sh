#!/usr/bin/env bash
# Bump Vera's version in one place and remind you to log it.
#
#   ./scripts/bump-version.sh 0.3.1
#
# - Updates CFBundleVersion + CFBundleShortVersionString in macos/Vera/build-app.sh
# - Prints the CHANGELOG + git-tag steps (kept manual so the release note is real)
set -euo pipefail

NEW="${1:-}"
if [[ ! "$NEW" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "usage: $0 X.Y.Z   (e.g. 0.3.1)"; exit 1
fi
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$REPO/macos/Vera/build-app.sh"

CUR="$(grep -oE 'CFBundleShortVersionString</key> <string>[0-9.]+' "$PLIST" | grep -oE '[0-9.]+$' | head -1)"
echo "Bumping Vera $CUR → $NEW"

# update both version keys
/usr/bin/sed -i '' "s#<key>CFBundleVersion</key>         <string>${CUR}</string>#<key>CFBundleVersion</key>         <string>${NEW}</string>#" "$PLIST"
/usr/bin/sed -i '' "s#<key>CFBundleShortVersionString</key> <string>${CUR}</string>#<key>CFBundleShortVersionString</key> <string>${NEW}</string>#" "$PLIST"

echo "✓ build-app.sh now at $NEW"
echo
echo "Next (manual, so the note is real):"
echo "  1. Add a '## [$NEW] — $(date +%Y-%m-%d)' section at the top of CHANGELOG.md"
echo "  2. ./macos/Vera/build-app.sh   # build the release"
echo "  3. git commit -am \"Vera v$NEW\" && git tag vera-v$NEW && git push --tags"
