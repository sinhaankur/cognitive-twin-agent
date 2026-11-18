#!/usr/bin/env bash
# Install Vera's brain as a user LaunchAgent, running from a NON-TCC location.
#
# macOS locks ~/Documents (TCC) for background services — that's why the app's
# forked Python hung and the first service attempt hit "Operation not permitted".
# Fix: COPY the Python brain into ~/Library/Application Support/Vera (not gated)
# and have launchd run it from there. Your ~/Documents repo stays the source;
# re-run this after changes to sync.
#
#   ./scripts/install-service.sh              install + (re)sync + start
#   ./scripts/install-service.sh --uninstall  stop + remove the agent
set -euo pipefail

LABEL="com.sinhaankur.vera.brain"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
VERA_HOME="$HOME/Library/Application Support/Vera"
AGENTS_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$HOME/Library/Logs/Vera"
PLIST_DST="$AGENTS_DIR/$LABEL.plist"
PLIST_SRC="$REPO/scripts/$LABEL.plist"
PORT="${CTWIN_PORT:-7878}"
UID_NUM="$(id -u)"

bootout() {
  launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
  launchctl unload "$PLIST_DST" 2>/dev/null || true
}

if [ "${1:-}" = "--uninstall" ]; then
  echo "Uninstalling $LABEL…"
  bootout
  rm -f "$PLIST_DST"
  echo "Done. (installed brain left in $VERA_HOME; logs in $LOG_DIR)"
  exit 0
fi

echo "Installing Vera brain service (non-TCC location)…"
mkdir -p "$AGENTS_DIR" "$LOG_DIR" "$VERA_HOME"

# 1) sync the brain OUT of ~/Documents into the non-TCC home. Only what the
#    server needs at runtime: the package, its policies, config, and the runner.
echo "  syncing brain → $VERA_HOME"
rsync -a --delete \
  --exclude '__pycache__' --exclude '*.pyc' \
  "$REPO/cognitive_twin" "$VERA_HOME/"
rsync -a --delete "$REPO/policies" "$VERA_HOME/" 2>/dev/null || true
# system_dna.md IS Vera's character — without it she runs the bland generic
# persona ("pragmatic, concise, no fluff"), which is why the chat felt like
# "talking to a prompt". It must live at VERA_HOME (parents[2] of the package).
cp -f "$REPO/system_dna.md" "$VERA_HOME/" 2>/dev/null || true
# Kokoro neural-voice worker (the model runs in its own py3.12 venv, set up once
# by scripts/setup-kokoro.sh). Sync the worker script; leave the venv + model.
cp -f "$REPO/scripts/kokoro_synth.py" "$VERA_HOME/" 2>/dev/null || true
cp -f "$REPO/agent_config.example.json" "$VERA_HOME/" 2>/dev/null || true
[ -f "$REPO/agent_config.json" ] && cp -f "$REPO/agent_config.json" "$VERA_HOME/" || true
install -m 0755 "$REPO/scripts/vera-brain.sh" "$VERA_HOME/vera-brain.sh"

# 2) write the LaunchAgent plist, pointing at the INSTALLED runner (not Documents)
echo "  writing LaunchAgent → $PLIST_DST"
sed -e "s#__VERA_HOME__#$VERA_HOME#g" -e "s#__LOGDIR__#$LOG_DIR#g" "$PLIST_SRC" > "$PLIST_DST"

# 3) (re)load it
bootout
if ! launchctl bootstrap "gui/$UID_NUM" "$PLIST_DST" 2>/dev/null; then
  launchctl load -w "$PLIST_DST"
fi
launchctl enable "gui/$UID_NUM/$LABEL" 2>/dev/null || true
launchctl kickstart -k "gui/$UID_NUM/$LABEL" 2>/dev/null || true

  echo "  waiting for the brain to answer on :${PORT} ..."
ok=0
for _ in $(seq 1 25); do
  sleep 1
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "http://127.0.0.1:$PORT/api/health" || true)"
  if [ "$code" = "200" ]; then ok=1; break; fi
done

if [ "$ok" = "1" ]; then
  echo "✓ Vera's brain is up (launchd-managed) at http://127.0.0.1:$PORT"
  echo "  logs: $LOG_DIR/brain.out.log  +  brain.err.log"

  # --- UNIFIED SERVICE: retire the old separate agents, now folded into the brain.
  # Only runs AFTER the unified brain is proven up (health check passed above), so
  # we never leave Vera without her helpers. The brain's vera-brain.sh now sets
  # OLLAMA_HOST itself and runs diagnostics on an internal 30-min loop.
  for OLD in com.sinhaankur.vera.diagnostics com.sinhaankur.ollama-host; do
    OLD_PLIST="$HOME/Library/LaunchAgents/$OLD.plist"
    if [ -f "$OLD_PLIST" ] || launchctl list 2>/dev/null | grep -q "$OLD"; then
      launchctl bootout "gui/$UID_NUM/$OLD" 2>/dev/null || true
      launchctl unload "$OLD_PLIST" 2>/dev/null || true
      [ -f "$OLD_PLIST" ] && mv "$OLD_PLIST" "$OLD_PLIST.retired" 2>/dev/null || true
      echo "  ↳ retired old agent: $OLD (folded into the brain)"
    fi
  done
  echo "✓ One unified Vera service — OLLAMA_HOST + diagnostics now live in the brain."
else
  echo "✗ Not answering yet. The reason will be in:"
  echo "    tail -40 \"$LOG_DIR/brain.err.log\""
  echo "  (Old agents were LEFT in place — the unified brain didn't come up.)"
fi
