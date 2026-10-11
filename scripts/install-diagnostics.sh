#!/usr/bin/env bash
# Install the scheduled Vera diagnostics agent: every 30 min it pings the local
# brain's /api/diagnose, which runs every check and appends a line to the
# day-to-day trend log. So the history builds itself from real usage.
#
#   bash scripts/install-diagnostics.sh          # install + start
#   bash scripts/install-diagnostics.sh --off     # stop + remove
#
# Read the trend any time:  python3 -m cognitive_twin.cli diagnose --trends
set -euo pipefail
cd "$(dirname "$0")/.."

LABEL="com.sinhaankur.vera.diagnostics"
AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/Vera"
PLIST_SRC="deployment/$LABEL.plist"
PLIST_DST="$AGENTS_DIR/$LABEL.plist"
VERA_HOME="$HOME/Library/Application Support/Vera"
UID_NUM="$(id -u)"

bootout() {
  launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
  launchctl unload "$PLIST_DST" 2>/dev/null || true
}

if [ "${1:-}" = "--off" ]; then
  bootout
  rm -f "$PLIST_DST"
  echo "✓ diagnostics agent removed. (The trend log stays; read it with: diagnose --trends)"
  exit 0
fi

mkdir -p "$AGENTS_DIR" "$LOG_DIR"
echo "  writing LaunchAgent → $PLIST_DST"
sed -e "s#__VERA_HOME__#$VERA_HOME#g" -e "s#__LOGDIR__#$LOG_DIR#g" "$PLIST_SRC" > "$PLIST_DST"

bootout
if ! launchctl bootstrap "gui/$UID_NUM" "$PLIST_DST" 2>/dev/null; then
  launchctl load -w "$PLIST_DST"
fi
launchctl enable "gui/$UID_NUM/$LABEL" 2>/dev/null || true
launchctl kickstart "gui/$UID_NUM/$LABEL" 2>/dev/null || true

echo "✓ Vera diagnostics scheduled (every 30 min)."
echo "  trend log: $LOG_DIR/diagnostics.jsonl"
echo "  read it:   python3 -m cognitive_twin.cli diagnose --trends"
echo "  turn off:  bash scripts/install-diagnostics.sh --off"
