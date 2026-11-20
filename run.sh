#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Vera — one-command launcher (cross-platform: macOS · Linux · WSL)
#
# The whole thing in ONE step: set up a venv on first run, install Vera, start her
# brain + voice server, and open the app. Everything stays on THIS machine —
# nothing is uploaded. (Modeled on WatchTower's run.sh; Mac users who want the
# native menu-bar Vera.app can also run macos/Vera/build-app.sh.)
#
# Usage:
#   ./run.sh              # set up (first run) + start the brain + open the UI
#   ./run.sh stop         # stop Vera's brain
#   ./run.sh logs         # tail the brain log
#   ./run.sh update       # git pull + reinstall deps, then restart
#   ./run.sh status       # is she up?
# ──────────────────────────────────────────────────────────────────────────────
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/.venv"
PORT="${VERA_PORT:-7878}"
LOG="${TMPDIR:-/tmp}/vera-brain.log"
PIDFILE="${TMPDIR:-/tmp}/vera-brain.pid"

# ── colours ───────────────────────────────────────────────────────────────────
GRN=$'\033[0;32m'; YEL=$'\033[1;33m'; RED=$'\033[0;31m'; CYN=$'\033[0;36m'; NC=$'\033[0m'
info()    { echo -e "${CYN}[Vera]${NC} $*"; }
success() { echo -e "${GRN}[Vera]${NC} $*"; }
warn()    { echo -e "${YEL}[Vera]${NC} $*"; }
error()   { echo -e "${RED}[Vera]${NC} $*" >&2; }

# load .env once so every mode shares the same local config
[[ -f "$ROOT/.env" ]] && { set -a; # shellcheck disable=SC1091
  source "$ROOT/.env"; set +a; }

# ── portable helpers ──────────────────────────────────────────────────────────
is_listening() {
  if command -v lsof >/dev/null 2>&1; then lsof -i ":$1" -sTCP:LISTEN -nP >/dev/null 2>&1
  elif command -v ss >/dev/null 2>&1; then ss -tlnH "sport = :$1" 2>/dev/null | grep -q .
  else curl -s -m 2 "http://127.0.0.1:$1/api/health" >/dev/null 2>&1; fi
}
open_url() {
  if command -v open >/dev/null 2>&1; then open "$1"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$1" >/dev/null 2>&1 &
  else info "Open $1 in your browser."; fi
}
pybin() { command -v python3 || command -v python; }

# ── setup: venv + install (idempotent; only does work when needed) ────────────
ensure_setup() {
  local py; py="$(pybin)"
  if [[ -z "$py" ]]; then error "Python 3 not found. Install Python 3.9+ and re-run."; exit 1; fi
  if [[ ! -d "$VENV" ]]; then
    info "First run — creating a private virtualenv (.venv)…"
    "$py" -m venv "$VENV"
  fi
  # shellcheck disable=SC1091
  source "$VENV/bin/activate" 2>/dev/null || source "$VENV/Scripts/activate"
  # install Vera (and the fast native crypto) only if the package isn't importable.
  if ! python -c "import cognitive_twin" >/dev/null 2>&1; then
    info "Installing Vera + dependencies (one-time)…"
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -e "$ROOT" cryptography || {
      error "Install failed — see the output above."; exit 1; }
    success "Installed."
  fi
  # a model to think with: prefer Ollama + her tuned model; warn, never block.
  if command -v ollama >/dev/null 2>&1; then
    curl -s -m 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 || (ollama serve >/dev/null 2>&1 &)
  else
    warn "Ollama not found — Vera thinks on a local model via Ollama (https://ollama.com)."
  fi
}

start() {
  if is_listening "$PORT"; then success "Vera is already running at http://127.0.0.1:$PORT"; open_url "http://127.0.0.1:$PORT"; return; fi
  ensure_setup
  info "Starting Vera's brain on :$PORT …"
  ( nohup python -m cognitive_twin.voice.server --no-open --port "$PORT" >"$LOG" 2>&1 & echo $! >"$PIDFILE" )
  for _ in $(seq 1 40); do is_listening "$PORT" && break; sleep 1; done
  if is_listening "$PORT"; then
    success "Vera is up — http://127.0.0.1:$PORT"
    open_url "http://127.0.0.1:$PORT"
  else
    error "She didn't come up in time. Logs: $LOG"; tail -n 20 "$LOG" 2>/dev/null
  fi
}

stop() {
  [[ -f "$PIDFILE" ]] && kill "$(cat "$PIDFILE")" 2>/dev/null
  pkill -f "cognitive_twin.voice.server" 2>/dev/null
  rm -f "$PIDFILE"
  success "Vera stopped."
}

case "${1:-start}" in
  ""|start|run) start ;;
  stop)         stop ;;
  restart)      stop; sleep 1; start ;;
  status)       is_listening "$PORT" && success "up (:$PORT)" || warn "not running" ;;
  logs)         tail -f "$LOG" ;;
  update)       info "Updating…"; git -C "$ROOT" pull --ff-only && rm -rf "$VENV" && ensure_setup && restart ;;
  *)            echo "usage: ./run.sh [start|stop|restart|status|logs|update]" ;;
esac
