"""
XTTS synthesis worker — runs inside the cloning venv (Python 3.11 + coqui-tts).

Two modes:
  one-shot:  python _xtts_say.py <text> <speaker_wav> <out_wav>
  server:    python _xtts_say.py --serve <speaker_wav>
             then write JSON lines {"text": "...", "out": "..."} to stdin;
             it keeps the model loaded so each line renders fast (no reload).

Tuned for a warm, steady clone of a real person's voice.
"""

import json
import sys
import warnings

warnings.filterwarnings("ignore")

# Quality knobs for XTTS-v2. Lower temperature = steadier/closer to the sample;
# repetition penalty curbs the model drifting; length penalty keeps pacing natural.
GEN_KWARGS = dict(
    language="en",
    temperature=0.55,          # steadier, more faithful to the reference
    length_penalty=1.0,
    repetition_penalty=3.0,    # reduce robotic loops/artefacts
    top_k=50,
    top_p=0.85,
    speed=1.0,
)


def _load():
    from TTS.api import TTS  # noqa
    # XTTS supports a direct synth path; TTS() wrapper is simplest + stable.
    return TTS("tts_models/multilingual/multi-dataset/xtts_v2")


def _render(tts, text, speaker_wav, out_wav):
    tts.tts_to_file(text=text, speaker_wav=speaker_wav, file_path=out_wav, **GEN_KWARGS)


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--serve":
        speaker = sys.argv[2]
        tts = _load()
        # ready signal so the parent knows the (slow) model load is done
        print(json.dumps({"ready": True}), flush=True)
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                _render(tts, req["text"], speaker, req["out"])
                print(json.dumps({"ok": True, "out": req["out"]}), flush=True)
            except Exception as e:  # never kill the worker on one bad line
                print(json.dumps({"ok": False, "error": str(e)}), flush=True)
        return

    # one-shot
    text, speaker_wav, out_wav = sys.argv[1], sys.argv[2], sys.argv[3]
    tts = _load()
    _render(tts, text, speaker_wav, out_wav)


if __name__ == "__main__":
    main()
