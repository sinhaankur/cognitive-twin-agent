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

# ── 0. prerequisites ────────────────────────────────────────────────────────
command -v git >/dev/null 2>&1 || { echo "git is required (install Xcode command line tools: xcode-select --install)"; exit 1; }
PY="$(command -v python3 || true)"
[ -z "$PY" ] && { echo "python3 is required (brew install python@3.12)"; exit 1; }

# ── 1. the brain ────────────────────────────────────────────────────────────
if [ -d "$REPO_DIR/.git" ]; then
  say "Updating the brain…"
  git -C "$REPO_DIR" pull --ff-only --quiet 2>/dev/null && ok "brain updated" || warn "couldn't fast-forward; leaving your copy as-is"
else
  say "Getting the brain…"
  mkdir -p "$HOME/Documents"
  git clone --quiet "$REPO_URL" "$REPO_DIR" && ok "brain cloned to $REPO_DIR"
fi

# ── 2. Ollama + a small model ───────────────────────────────────────────────
if command -v ollama >/dev/null 2>&1; then
  say "Ollama found — pulling a small model + the embedder…"
  (ollama pull qwen2.5:7b  >/dev/null 2>&1 && ok "qwen2.5:7b ready")   || warn "pull qwen2.5:7b yourself later"
  (ollama pull nomic-embed-text >/dev/null 2>&1 && ok "embedder ready") || warn "pull nomic-embed-text later"
else
  warn "Ollama not installed — Vera's reasoning needs it."
  warn "Install it from https://ollama.com, then re-run this script."
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
echo "${GRN}${BOLD}Vera is set up.${RST}"
echo "Open ${BOLD}Vera.app${RST} (download it from the releases page), and click the orb to talk."
echo "${DIM}First launch: right-click the app → Open (it's ad-hoc signed, not notarized).${RST}"
