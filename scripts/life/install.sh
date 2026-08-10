#!/usr/bin/env bash
# install.sh — put the `life` command on your PATH (no Vera app required).
#
# Symlinks `life` into a bin dir on your PATH (~/.local/bin by default). After
# this, anyone can run `life` from anywhere to open the dashboard or track things.
#
# Usage:  bash scripts/life/install.sh            # install
#         bash scripts/life/install.sh uninstall  # remove
#
# © Ankur Sinha. Personal use.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="${LIFE_BIN:-$HOME/.local/bin}"
TARGET="$BIN/life"

if [[ "${1:-}" == "uninstall" ]]; then
  rm -f "$TARGET"
  echo "Removed $TARGET."
  exit 0
fi

mkdir -p "$BIN"
chmod +x "$HERE/life"
ln -sf "$HERE/life" "$TARGET"
echo "✓ Installed: $TARGET  →  $HERE/life"

# PATH hint
case ":$PATH:" in
  *":$BIN:"*) echo "  ($BIN is already on your PATH — run: life)";;
  *) echo "  Add $BIN to your PATH, e.g.:"
     echo "    echo 'export PATH=\"$BIN:\$PATH\"' >> ~/.zshrc && source ~/.zshrc"
     echo "  then run:  life";;
esac

echo ""
echo "Try:"
echo "  life            # open the visual dashboard in your browser"
echo "  life status     # everything tracked, one screen"
echo "  life doctor     # security check"
