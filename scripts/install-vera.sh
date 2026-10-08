#!/usr/bin/env bash
# Vera — one-line installer.
#
#   curl -fsSL https://raw.githubusercontent.com/sinhaankur/cognitive-twin-agent/main/scripts/install-vera.sh | bash
#
# Sets up everything the Vera.app needs on this Mac:
#   1. the Python brain (clones/updates the repo)
#   2. Ollama + a small local model (if Ollama is present)
#   3. Vera's neural voice (Kokoro) — optional, best-effort
#   4. the launchd brain service
#
# Fully on-device. Nothing is uploaded. Re-run any time to update.
set -uo pipefail

REPO_URL="https://github.com/sinhaankur/cognitive-twin-agent.git"
REPO_DIR="$HOME/Documents/cognitive-twin-agent"
BOLD=$'\033[1m'; DIM=$'\033[2m'; GRN=$'\033[32m'; YEL=$'\033[33m'; RST=$'\033[0m'

say()  { echo "${BOLD}▸${RST} $*"; }
ok()   { echo "  ${GRN}✓${RST} $*"; }
warn() { echo "  ${YEL}!${RST} $*"; }

echo "${BOLD}Installing Vera — your on-device companion${RST}"
echo "${DIM}Everything runs on this Mac. Nothing is uploaded.${RST}"
echo

# ── 0. prerequisites — AUTO-INSTALL what's missing (don't make the user do it) ─
# The whole point is that a non-technical person runs ONE command. So instead of
# bailing when git/python/Ollama are absent, we install them (via Homebrew, the
# standard macOS package manager), with clear progress. Each step is best-effort
# and explains itself if it can't proceed.

# Homebrew — the package manager everything else installs through.
BREW="$(command -v brew || true)"
if [ -z "$BREW" ]; then
  [ -x /opt/homebrew/bin/brew ] && BREW=/opt/homebrew/bin/brew          # Apple Silicon
  [ -z "$BREW" ] && [ -x /usr/local/bin/brew ] && BREW=/usr/local/bin/brew  # Intel
fi
if [ -z "$BREW" ]; then
  say "Installing Homebrew (the macOS package manager)… ${DIM}(may ask for your password)${RST}"
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" \
    && ok "Homebrew installed" || warn "Homebrew install didn't complete — see https://brew.sh"
  [ -x /opt/homebrew/bin/brew ] && BREW=/opt/homebrew/bin/brew
  [ -z "$BREW" ] && [ -x /usr/local/bin/brew ] && BREW=/usr/local/bin/brew
fi
[ -n "$BREW" ] && eval "$("$BREW" shellenv)" 2>/dev/null || true

# git — needed to fetch the brain. (Xcode CLT ships one; Homebrew is the fallback.)
if ! command -v git >/dev/null 2>&1; then
  say "Installing git…"
  [ -n "$BREW" ] && "$BREW" install git >/dev/null 2>&1 && ok "git installed" \
    || { xcode-select --install 2>/dev/null; warn "installing the developer tools (git) — if a window opened, finish it and re-run this."; }
fi
command -v git >/dev/null 2>&1 || { echo "git is still missing — install the Xcode Command Line Tools (xcode-select --install), then re-run."; exit 1; }

# python3 — the brain's runtime.
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
  say "Installing Python…"
  [ -n "$BREW" ] && "$BREW" install python@3.12 >/dev/null 2>&1 && PY="$(command -v python3 || true)" && ok "Python installed"
fi
[ -z "$PY" ] && { echo "python3 is still missing — install it from https://python.org, then re-run."; exit 1; }

# Ollama — the local model engine. Auto-install so the user never has to.
if ! command -v ollama >/dev/null 2>&1 && [ ! -x /Applications/Ollama.app/Contents/MacOS/ollama ]; then
  say "Installing Ollama (the local model engine)…"
  [ -n "$BREW" ] && "$BREW" install --cask ollama >/dev/null 2>&1 && ok "Ollama installed" \
    || warn "couldn't auto-install Ollama — get it from https://ollama.com, then re-run."
fi

# ── 1. the brain ────────────────────────────────────────────────────────────
if [ -d "$REPO_DIR/.git" ]; then
  say "Updating the brain…"
  git -C "$REPO_DIR" pull --ff-only --quiet 2>/dev/null && ok "brain updated" || warn "couldn't fast-forward; leaving your copy as-is"
else
  say "Getting the brain…"
  mkdir -p "$HOME/Documents"
  git clone --quiet "$REPO_URL" "$REPO_DIR" && ok "brain cloned to $REPO_DIR"
fi

# ── 2. Ollama + the RIGHT-SIZED model for THIS machine ──────────────────────
# Don't pull a 4.7 GB 7B onto an 8 GB laptop. Ask the brain which model suits
# this Mac's RAM — the smallest that's genuinely capable — so the first-run
# download stays as light as the hardware allows.
if command -v ollama >/dev/null 2>&1; then
  MODEL="$("$PY" -c 'import sys; sys.path.insert(0,"'"$REPO_DIR"'"); from cognitive_twin import device_model as d; print(d.recommend_pull())' 2>/dev/null || echo "qwen2.5:3b")"
  # her trained model lives in the repo (a Modelfile), not the Ollama registry —
  # build it locally; everything else pulls from the registry.
  if [ "$MODEL" = "vera-tuned" ] && [ -f "$REPO_DIR/training/vera-tuned.Modelfile" ]; then
    say "Building her trained voice (vera-tuned, a light 3B)…"
    (ollama create vera-tuned -f "$REPO_DIR/training/vera-tuned.Modelfile" >/dev/null 2>&1 && ok "vera-tuned ready") \
      || { warn "couldn't build vera-tuned — pulling a small base instead"; MODEL="qwen2.5:3b"; ollama pull qwen2.5:3b >/dev/null 2>&1 && ok "qwen2.5:3b ready"; }
  else
    say "Pulling the right model for this Mac (${BOLD}${MODEL}${RST})…"
    (ollama pull "$MODEL" >/dev/null 2>&1 && ok "$MODEL ready") || warn "pull $MODEL yourself later"
  fi
  (ollama pull nomic-embed-text >/dev/null 2>&1 && ok "embedder ready") || warn "pull nomic-embed-text later"
else
  warn "Ollama not installed — Vera's reasoning needs it."
  warn "Install it from https://ollama.com, then re-run this script (it'll pick the right-sized model for your Mac)."
fi

# ── 3. the neural voice (Kokoro) — optional ─────────────────────────────────
if [ -x "$REPO_DIR/scripts/setup-kokoro.sh" ]; then
  say "Setting up Vera's voice (Kokoro)… ${DIM}(optional, downloads a model)${RST}"
  bash "$REPO_DIR/scripts/setup-kokoro.sh" >/dev/null 2>&1 && ok "neural voice ready" \
    || warn "voice setup skipped — she'll use the system voice (run setup-kokoro.sh later)"
fi

# ── 4. the brain service ────────────────────────────────────────────────────
say "Starting Vera's brain as a background service…"
bash "$REPO_DIR/scripts/install-service.sh" >/dev/null 2>&1 && ok "brain service running" \
  || warn "service didn't start — see ~/Library/Logs/Vera/brain.err.log"

echo
echo "${GRN}${BOLD}Her brain is set up and running.${RST}"
echo "Last step — get the app:"
echo "  1. Download ${BOLD}Vera.app${RST}: https://github.com/sinhaankur/cognitive-twin-agent/releases/latest"
echo "  2. Unzip it and move ${BOLD}Vera.app${RST} to /Applications"
echo "  3. First launch: ${BOLD}right-click → Open${RST} (ad-hoc signed, not notarized), then click the orb."
