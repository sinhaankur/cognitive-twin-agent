#!/usr/bin/env bash
# Set up LOCAL voice cloning for Anita — so she can speak in a loved one's actual
# voice, entirely on your machine. Nothing is uploaded.
#
#   ./scripts/setup-voice-clone.sh
#
# What it does:
#   - Uses `uv` to create an isolated Python 3.11 env at ~/.cognitive-twin/tts-venv
#     (the cloning libs need 3.9–3.11; your system Python can stay whatever it is).
#   - Installs Coqui TTS (XTTS-v2) + torch into that env only.
#   - Installs ffmpeg (via brew) for audio prep, if missing.
#
# After this, `cognitive_twin.voice_clone` auto-detects the engine and Anita
# renders her replies in the cloned voice. ~a few GB download; one-time.

set -euo pipefail

VENV="$HOME/.cognitive-twin/tts-venv"

echo "Cognitive Twin — local voice cloning setup"
echo "This stays entirely on your machine. Nothing is uploaded."
echo

if ! command -v uv >/dev/null 2>&1; then
  echo "Need 'uv' (https://docs.astral.sh/uv/). Install: brew install uv" >&2
  exit 1
fi

# ffmpeg for converting recordings to the wav the cloner wants
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[1/3] Installing ffmpeg (audio prep)..."
  brew install ffmpeg || echo "  (couldn't auto-install ffmpeg; install it manually if audio conversion fails)"
else
  echo "[1/3] ffmpeg present."
fi

echo "[2/3] Creating isolated Python 3.11 env at $VENV ..."
mkdir -p "$HOME/.cognitive-twin"
uv venv --python 3.11 "$VENV"

echo "[3/3] Installing Coqui TTS (XTTS-v2) + torch into the env (a few GB)..."
# coqui-tts is the maintained fork of the original TTS package.
uv pip install --python "$VENV/bin/python" "coqui-tts" "torch" "torchaudio" || \
  uv pip install --python "$VENV/bin/python" "TTS" "torch" "torchaudio"

echo
echo "Done. The cloning engine lives at: $VENV/bin/python"
echo "Anita auto-detects it (CTWIN_TTS_PYTHON can override the path)."
echo
echo "Next:"
echo "  1. Give Anita the voice sample:"
echo "     python -m cognitive_twin.voice_clone set /path/to/mother_voice_clean.wav \"Mom\""
echo "  2. Test it:"
echo "     python -m cognitive_twin.voice_clone say \"Good morning, beta.\""
