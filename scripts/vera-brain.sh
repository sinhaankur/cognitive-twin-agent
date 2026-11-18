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
# ONE consistent, fast voice: Kokoro (af_heart). Disables the slow/switching
# XTTS clone in /api/speak. Override with CTWIN_VOICE_KOKORO_ONLY=0 to re-enable.
export CTWIN_VOICE_KOKORO_ONLY="${CTWIN_VOICE_KOKORO_ONLY:-1}"
export PYTHONUNBUFFERED=1
# the package + policies live right here in VERA_HOME
export PYTHONPATH="$VERA_HOME:${PYTHONPATH:-}"

# --- UNIFIED SERVICE: one agent does everything (was 3 separate agents) ---------
# Folded in so there's ONE clean flow instead of a sprawl of launchd agents:
#
#   1) OLLAMA_HOST — where the model backend lives. Was a separate `ollama-host`
#      plist that only ran `launchctl setenv`. Now set right here at startup.
#      Override by exporting CTWIN_OLLAMA_HOST before launch.
export OLLAMA_HOST="${CTWIN_OLLAMA_HOST:-${OLLAMA_HOST:-100.91.27.70:11434}}"

#   2) Diagnostics — was a separate `vera.diagnostics` agent that curl'd
#      /api/diagnose every 30 min. Now a tiny internal loop in this same service,
#      so health tracking lives WITH the brain (one lifecycle, nothing to forget).
#      Writes the same trend log; read it with: ctwin diagnose --trends.
#      Disable with CTWIN_SELF_DIAGNOSE=0.
if [ "${CTWIN_SELF_DIAGNOSE:-1}" = "1" ]; then
  (
    sleep 120  # let the brain fully warm before the first probe
    while true; do
      curl -fsS "http://127.0.0.1:${PORT}/api/diagnose" >/dev/null 2>&1 || true
      sleep 1800  # every 30 min, matching the old agent
    done
  ) &
fi

exec "$PY" -m cognitive_twin.voice.server --no-open --port "$PORT"
