#!/usr/bin/env bash
# Vera's brain, run as a SERVICE (by launchd) — from a NON-TCC location.
#
# Why this exists: the code lives in ~/Documents, which macOS locks (TCC) for
# background/forked processes — the real reason the app-spawned Python children
# hung at 14 MB and this agent first failed with "Operation not permitted".
# So the brain is INSTALLED to ~/Library/Application Support/Vera (not TCC-gated)
# and run from there. launchd keeps it alive, restarts on crash, logs to a file.
#
# Env:
#   VERA_HOME   install dir (default ~/Library/Application Support/Vera)
#   CTWIN_PY    python to use (default: first real python3 found)
#   CTWIN_PORT  voice server port (default 7878)
set -uo pipefail

VERA_HOME="${VERA_HOME:-$HOME/Library/Application Support/Vera}"
PORT="${CTWIN_PORT:-7878}"

pick_python() {
  if [ -n "${CTWIN_PY:-}" ] && [ -x "${CTWIN_PY}" ]; then echo "$CTWIN_PY"; return; fi
  for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    [ -x "$p" ] && { echo "$p"; return; }
  done
  echo "python3"
}
PY="$(pick_python)"

cd "$VERA_HOME" || exit 1

export CTWIN_WEB="${CTWIN_WEB:-1}"
export COQUI_TOS_AGREED="${COQUI_TOS_AGREED:-1}"
export PYTHONUNBUFFERED=1
# the package + policies live right here in VERA_HOME
export PYTHONPATH="$VERA_HOME:${PYTHONPATH:-}"

exec "$PY" -m cognitive_twin.voice.server --no-open --port "$PORT"
