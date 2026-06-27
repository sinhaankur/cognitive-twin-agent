"""
Voice A/B harness — render the SAME text through different (reference, settings)
profiles so you can listen and pick which sounds most like the real person.

Non-destructive: it never touches the live reference or the agent. It just writes
ab_<profile>.wav files into the voice dir for you to play with `afplay`.

Runs inside the cloning venv (Python 3.11 + coqui-tts). Loads the XTTS model once
and reuses it across every profile, so a full sweep is fast.

Usage (from the repo root):
    "$HOME/.cognitive-twin/tts-venv/bin/python" scripts/voice_ab.py "Some sentence to say."

Each profile pairs a reference WAV with a set of synthesis knobs. Edit PROFILES
below to explore. The console prints exactly what to `afplay`.
"""

import json
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

VOICE_DIR = Path(os.environ.get("CTWIN_MEMORY_DIR", Path.home() / ".cognitive-twin")) / "voice"

# Reference candidates (created by the surrounding shell prep). Falls back to
# whatever exists so the harness still runs on a fresh machine.
REF_22K = VOICE_DIR / "reference.original-backup.wav"   # the original 22.05k sample
REF_24K_PLAIN = VOICE_DIR / "reference_24k_plain.wav"   # straight 24k upsample
REF_24K_GENTLE = VOICE_DIR / "reference_24k_gentle.wav" # 24k + gentle cleaning


def _first_existing(*paths: Path) -> Path:
    for p in paths:
        if p.is_file():
            return p
    # last resort: the live reference
    return VOICE_DIR / "reference.wav"


# Each profile: (label, reference_wav, gen_kwargs). The labels become file names:
#   ab_<label>.wav
PROFILES = [
    # The current shipped settings — the baseline you're hearing today.
    ("current", _first_existing(REF_22K), dict(
        temperature=0.55, length_penalty=1.0, repetition_penalty=3.0,
        top_k=50, top_p=0.85, speed=1.0,
    )),
    # Just fix the sample rate (24k native), keep current knobs.
    ("24k_only", _first_existing(REF_24K_PLAIN, REF_22K), dict(
        temperature=0.55, length_penalty=1.0, repetition_penalty=3.0,
        top_k=50, top_p=0.85, speed=1.0,
    )),
    # 24k + gentle cleaning + softened knobs (more natural prosody).
    ("tuned", _first_existing(REF_24K_GENTLE, REF_24K_PLAIN, REF_22K), dict(
        temperature=0.65, length_penalty=1.0, repetition_penalty=2.0,
        top_k=50, top_p=0.85, speed=1.0, enable_text_splitting=True,
    )),
    # Faithful: lowest temperature, hews closest to the timbre of the sample.
    ("faithful", _first_existing(REF_24K_GENTLE, REF_24K_PLAIN, REF_22K), dict(
        temperature=0.45, length_penalty=1.0, repetition_penalty=2.0,
        top_k=40, top_p=0.80, speed=1.0, enable_text_splitting=True,
    )),
]


def _detect_language(text: str) -> str:
    if any('ऀ' <= ch <= 'ॿ' for ch in text):
        return "hi"
    return "en"


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: voice_ab.py \"text to synthesize\"")
        return 2
    text = sys.argv[1]
    lang = _detect_language(text)

    from TTS.api import TTS
    print(json.dumps({"status": "loading model (one-time)…"}), flush=True)
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")

    rendered = []
    for label, ref, kwargs in PROFILES:
        out = VOICE_DIR / f"ab_{label}.wav"
        try:
            tts.tts_to_file(text=text, speaker_wav=str(ref), file_path=str(out),
                            language=lang, **kwargs)
            rendered.append((label, ref.name, out))
            print(json.dumps({"ok": True, "profile": label, "ref": ref.name,
                              "out": str(out)}), flush=True)
        except Exception as e:
            print(json.dumps({"ok": False, "profile": label, "error": str(e)}), flush=True)

    print("\n=== listen (each profile, same words) ===")
    for label, refname, out in rendered:
        print(f"  afplay '{out}'   # {label}  (ref: {refname})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
