#!/usr/bin/env bash
# One-time setup for Vera's Kokoro neural voice (expressive, human-sounding).
#
#   ./scripts/setup-kokoro.sh
#
# Creates a dedicated Python 3.12 venv under VERA_HOME, installs Kokoro, and
# drops the warm-worker script. Kokoro needs espeak-ng (brew install espeak-ng).
# Re-run safely; it skips what's already present. After this, run
# ./scripts/install-service.sh to (re)start the brain with the voice available.
set -uo pipefail

VERA_HOME="${VERA_HOME:-$HOME/Library/Application Support/Vera}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"

echo "Setting up Vera's Kokoro voice…"
mkdir -p "$VERA_HOME"

# 1. espeak-ng (Kokoro's phonemizer)
if ! command -v espeak-ng >/dev/null 2>&1; then
  echo "  installing espeak-ng (brew)…"
  brew install espeak-ng || { echo "  ! install espeak-ng manually, then re-run"; exit 1; }
fi

# 2. a py3.12 venv (spacy/kokoro don't build on 3.14 yet)
PY312="$(command -v python3.12 || echo /opt/homebrew/opt/python@3.12/bin/python3.12)"
if [ ! -x "$PY312" ]; then
  echo "  ! need python3.12 — 'brew install python@3.12', then re-run"; exit 1
fi
if [ ! -x "$VERA_HOME/kokoro-venv/bin/python3" ]; then
  echo "  creating kokoro venv…"
  "$PY312" -m venv "$VERA_HOME/kokoro-venv"
fi

# 3. kokoro + soundfile
echo "  installing kokoro + soundfile (first time downloads a bit)…"
"$VERA_HOME/kokoro-venv/bin/pip" install --quiet --upgrade pip >/dev/null 2>&1 || true
"$VERA_HOME/kokoro-venv/bin/pip" install --quiet kokoro soundfile || {
  echo "  ! kokoro install failed"; exit 1; }

# 4. the warm-worker script
cp -f "$REPO/scripts/kokoro_synth.py" "$VERA_HOME/kokoro_synth.py"

# 5. warm it once so the model + spacy data download now, not on first reply
echo "  warming the model (one-time download)…"
printf '%s\n' '{"text":"ready","voice":"af_bella","speed":0.92}' \
  | "$VERA_HOME/kokoro-venv/bin/python3" "$VERA_HOME/kokoro_synth.py" >/dev/null 2>&1 &
WPID=$!; sleep 25; kill "$WPID" 2>/dev/null || true

echo "✓ Kokoro ready. Default voice: Bella (af_bella)."
echo "  Now run: ./scripts/install-service.sh"
