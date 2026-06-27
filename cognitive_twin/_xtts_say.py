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

# Quality knobs for XTTS-v2, tuned for a short (~7s) real-person reference.
# temperature 0.65 gives natural prosody without drifting off the timbre; a lower
# value (e.g. 0.45) hews closer to the sample but tends to rush/flatten delivery.
# repetition_penalty 2.0 (was 3.0) avoids the lifeless, clipped pacing the higher
# value caused. text splitting keeps long replies from drifting partway through.
# (language is chosen per-utterance — see _detect_language.)
GEN_KWARGS = dict(
    temperature=0.65,          # natural prosody, still faithful to the reference
    length_penalty=1.0,
    repetition_penalty=2.0,    # curb artefacts without flattening the voice
    top_k=50,
    top_p=0.85,
    speed=1.0,
    enable_text_splitting=True,  # synthesize long replies in stable chunks
)

# A few common Hinglish (Hindi-in-Latin-letters) words. If the text is clearly
# Hindi — Devanagari or these cues — render with the Hindi voice so an Indian
# parent's accent and cadence come through naturally.
_HINGLISH = {
    "beta", "beti", "hai", "nahi", "nahin", "kya", "kaise", "kaisa", "theek",
    "thik", "accha", "acha", "haan", "ji", "aaj", "kal", "khana", "khaya",
    "ghar", "maa", "papa", "bahut", "bohot", "pyaar", "pyar", "chai", "namaste",
    "shukriya", "dhanyavaad", "bhai", "behen", "didi", "mummy",
}


def _detect_language(text: str) -> str:
    """Pick the XTTS language for this text: Hindi for Devanagari or clear
    Hinglish, otherwise English. Keeps a loved one's real accent."""
    # Devanagari block → Hindi
    if any('ऀ' <= ch <= 'ॿ' for ch in text):
        return "hi"
    words = [w.strip(".,!?").lower() for w in text.split()]
    if words:
        hits = sum(1 for w in words if w in _HINGLISH)
        if hits >= max(1, len(words) * 0.15):   # ~15%+ Hinglish → Hindi
            return "hi"
    return "en"


def _load():
    from TTS.api import TTS  # noqa
    # XTTS supports a direct synth path; TTS() wrapper is simplest + stable.
    return TTS("tts_models/multilingual/multi-dataset/xtts_v2")


def _render(tts, text, speaker_wav, out_wav, lang=None):
    language = lang or _detect_language(text)
    tts.tts_to_file(text=text, speaker_wav=speaker_wav, file_path=out_wav,
                    language=language, **GEN_KWARGS)


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
