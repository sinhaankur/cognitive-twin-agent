#!/usr/bin/env bash
# Turn a video (or several) of a loved one into their cloned voice for Vera —
# one command, entirely on your machine. Nothing is uploaded.
#
#   ./scripts/clone-voice-from-video.sh "Mom" ~/Videos/birthday.mov [more videos...]
#
# What it does:
#   1. Runs Voice Harvester to ISOLATE just their voice from each video
#      (Demucs strips music / background / other speakers), cleaned to the WAV
#      format XTTS wants. Multiple videos are merged into one richer sample.
#   2. Sets that WAV as the twin's cloned voice.
#   3. Speaks a test line so you can hear it right away.
#
# Prereqs (the script checks these and tells you how to fix them):
#   - Voice Harvester cloned (default: ~/Documents/voice-harvester; override
#     with VOICE_HARVESTER=/path).
#   - ffmpeg installed (brew install ffmpeg).
#   - The cloning engine set up once:  ./scripts/setup-voice-clone.sh
#   - For best isolation:  ~/.cognitive-twin/tts-venv/bin/pip install demucs
#
# Tips for a good clone: aim for ~1–2 min of clear speech total across your
# videos; quality beats length. Pass several clips to enrich the sample.

set -euo pipefail

# ---- args --------------------------------------------------------------------
if [ "$#" -lt 2 ]; then
  echo "usage: $0 \"Name\" video1 [video2 ...]" >&2
  echo "  e.g. $0 \"Mom\" ~/Videos/birthday.mov ~/Videos/call.mp4" >&2
  exit 2
fi

PERSON="$1"; shift
VIDEOS=("$@")

HARVESTER="${VOICE_HARVESTER:-$HOME/Documents/voice-harvester}"
OUT_DIR="${VOICE_OUT:-$HOME/.cognitive-twin/voice-work}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Vera — clone a loved one's voice from video"
echo "Everything stays on your machine. Nothing is uploaded."
echo

# ---- checks ------------------------------------------------------------------
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "✗ ffmpeg not found. Install it:  brew install ffmpeg" >&2
  exit 1
fi
if [ ! -f "$HARVESTER/cli.py" ]; then
  echo "✗ Voice Harvester not found at: $HARVESTER" >&2
  echo "  Clone it:  git clone https://github.com/sinhaankur/voice-harvester \"$HARVESTER\"" >&2
  echo "  Or point at it:  VOICE_HARVESTER=/path/to/voice-harvester $0 ..." >&2
  exit 1
fi
for v in "${VIDEOS[@]}"; do
  if [ ! -f "$v" ]; then
    echo "✗ no such file: $v" >&2
    exit 1
  fi
done

# ---- 1. build the ideal XTTS reference --------------------------------------
echo "[1/3] Perfecting $PERSON's voice from ${#VIDEOS[@]} file(s)…"
mkdir -p "$OUT_DIR"
SAMPLE="$OUT_DIR/${PERSON// /_}_reference.wav"

# refine.py isolates the voice (Demucs), transcribes, groups speakers, scores
# every segment, and keeps only the single cleanest window — then renders the
# 24kHz mono reference XTTS clones best from. With several videos, it refines
# each and picks the best overall. Prints a quality report + warnings.
if [ -f "$HARVESTER/refine.py" ]; then
  BEST=""; BEST_SNR="-999"; REPORT=""
  for v in "${VIDEOS[@]}"; do
    base="$(basename "${v%.*}")"
    ref="$OUT_DIR/${base}_ref.wav"
    echo "    · $base"
    OUT_JSON="$(python3 "$HARVESTER/refine.py" "$v" --out "$ref" 2>/dev/null || true)"
    # pull duration + snr from the JSON result (grep keeps this dependency-free)
    snr="$(printf '%s' "$OUT_JSON" | grep -o '"snr_db":[^,]*' | head -1 | grep -o '[-0-9.]*' || echo 0)"
    if [ -f "$ref" ] && awk "BEGIN{exit !($snr > $BEST_SNR)}"; then
      BEST="$ref"; BEST_SNR="$snr"; REPORT="$OUT_JSON"
    fi
  done
  if [ -n "$BEST" ] && [ -f "$BEST" ]; then
    cp "$BEST" "$SAMPLE"
    echo
    echo "  ── quality report ──"
    printf '%s\n' "$REPORT" | grep -oE '"(report|warnings)":\[[^]]*\]' \
      | sed 's/"report":\[//; s/"warnings":\[/  warnings: /; s/\]//; s/","/\n    • /g; s/"/    • /g' \
      || printf '%s\n' "$REPORT"
    echo "  ────────────────────"
  fi
fi

# Fallback: if refine.py isn't present or produced nothing, use the classic
# extractor (isolate + merge). Always leaves a usable sample.
if [ -z "${SAMPLE:-}" ] || [ ! -f "$SAMPLE" ]; then
  echo "    (using classic extractor)"
  python3 "$HARVESTER/cli.py" "${VIDEOS[@]}" -o "$OUT_DIR" --merge
  if [ -f "$OUT_DIR/combined_voice_sample.wav" ]; then
    SAMPLE="$OUT_DIR/combined_voice_sample.wav"
  else
    SAMPLE="$(ls -t "$OUT_DIR"/*_voice.wav 2>/dev/null | head -1 || true)"
  fi
fi

if [ -z "$SAMPLE" ] || [ ! -f "$SAMPLE" ]; then
  echo "✗ voice extraction produced no WAV in $OUT_DIR — check the messages above." >&2
  exit 1
fi
echo "    → reference: $SAMPLE"
echo "    (tip: give it a listen — 'open \"$SAMPLE\"' — before cloning)"

# ---- 2. set it as the cloned voice ------------------------------------------
echo "[2/3] Giving $PERSON's voice to your twin…"
cd "$REPO_ROOT"
python3 -m cognitive_twin.voice_clone set "$SAMPLE" "$PERSON"

# ---- 3. test it --------------------------------------------------------------
echo "[3/3] Speaking a test line in $PERSON's voice…"
python3 -m cognitive_twin.voice_clone say "Hello. I'm still here with you."

echo
echo "Done. From now on your twin speaks in $PERSON's voice."
echo "  • not right yet? re-run with more / cleaner clips (quality beats length)."
echo "  • undo any time:  python3 -m cognitive_twin.voice_clone clear"
