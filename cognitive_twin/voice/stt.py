"""
Speech-to-text via local Whisper — optional, local-first.

Uses faster-whisper if installed (fast, CTranslate2 backend); falls back to
openai-whisper if that's what's present. If neither is installed, is_available()
returns False and the web UI uses the browser's own speech recognition instead —
so the app still works, it just moves transcription into the browser.

    pip install faster-whisper      # recommended
"""

from __future__ import annotations

import sys
from functools import lru_cache
from typing import Any


def _which_backend() -> str | None:
    try:
        import faster_whisper  # noqa: F401
        return "faster_whisper"
    except ImportError:
        pass
    try:
        import whisper  # noqa: F401
        return "openai_whisper"
    except ImportError:
        return None


def is_available() -> bool:
    """True if any local Whisper backend can be imported."""
    return _which_backend() is not None


@lru_cache(maxsize=2)
def _load(model_size: str) -> tuple[str, Any]:
    """Load (and cache) a Whisper model. Returns (backend, model)."""
    backend = _which_backend()
    if backend == "faster_whisper":
        from faster_whisper import WhisperModel
        # int8 on CPU is a good default for a personal machine
        return backend, WhisperModel(model_size, device="auto", compute_type="int8")
    if backend == "openai_whisper":
        import whisper
        return backend, whisper.load_model(model_size)
    raise RuntimeError(
        "No local Whisper backend installed. Run `pip install faster-whisper`."
    )


def _default_model() -> str:
    """Model for live dictation. Default `small` (MULTILINGUAL, not small.en) so it
    understands Indian-accented English AND Hindi — and code-switching between them
    ("Vera, light on karo"), which the English-only models can't. Still fine on CPU.
    Override with CTWIN_STT_MODEL (small.en = English-only/faster, medium = most
    accurate/slower, tiny = lowest latency)."""
    import os
    return (os.environ.get("CTWIN_STT_MODEL") or "small").strip()


def _language() -> str | None:
    """Which language to decode. Default 'en' keeps latency low, but set
    CTWIN_STT_LANG=hi for Hindi, or CTWIN_STT_LANG=auto to let Whisper detect it
    per utterance (best for mixing English + Hindi freely). None = auto-detect."""
    import os
    v = (os.environ.get("CTWIN_STT_LANG") or "en").strip().lower()
    return None if v in ("auto", "detect", "") else v


def warm(model_size: str | None = None) -> None:
    """Preload the model so the first real utterance isn't a 20–30s cold load."""
    try:
        _load(model_size or _default_model())
    except Exception:
        pass


def _decode_opts() -> dict:
    """The tuned faster-whisper options, shared by both transcribe paths. Tuned for:
      • understanding you THROUGH background music + catching short phrases
        (beam_size=5, VAD with short min-silence + speech-pad, no cross-chunk
        conditioning so music doesn't make it loop/hallucinate), AND
      • YOUR way of speaking — Indian English + Hindi + code-switching
        (multilingual model + the language setting) with a PERSONAL hint of your
        own words/names (initial_prompt) so it hears them right."""
    import os
    opts: dict = {
        "beam_size": int(os.environ.get("CTWIN_STT_BEAM", "5") or "5"),
        "vad_filter": True,
        "vad_parameters": {
            "threshold": float(os.environ.get("CTWIN_STT_VAD", "0.5") or "0.5"),
            "min_silence_duration_ms": 300,
            "speech_pad_ms": 200,
        },
        "language": _language(),            # None = auto-detect (English+Hindi mix)
        "condition_on_previous_text": False,
        "temperature": [0.0, 0.2, 0.4],
        "no_speech_threshold": 0.6,
    }
    try:
        from .. import pronounce
        hint = pronounce.prompt()
        if hint:
            opts["initial_prompt"] = hint   # bias toward your names + Hindi/EN words
    except Exception:
        pass
    return opts


def transcribe(audio_path: str, *, model_size: str | None = None) -> str:
    """Transcribe an audio file to text using local Whisper. Raises if no
    backend is installed (callers should check is_available() first or catch)."""
    backend, model = _load(model_size or _default_model())
    if backend == "faster_whisper":
        segments, _info = model.transcribe(audio_path, **_decode_opts())
        return " ".join(seg.text for seg in segments).strip()
    # openai-whisper
    result = model.transcribe(audio_path, language=_language() or "en",
                              condition_on_previous_text=False)
    return str(result.get("text", "")).strip()


def transcribe_detail(audio_path: str, *, model_size: str | None = None) -> dict:
    """Like transcribe(), but also reports how SURE it was it was speech — so a
    caller can reject background music / a TV bleeding in ('background vs in-frame').
    Returns {text, no_speech_prob, avg_logprob, music_like}. music_like=True means
    'this looks like noise/music, not you talking to me' — don't act on it."""
    backend, model = _load(model_size or _default_model())
    if backend != "faster_whisper":
        # openai-whisper path has no cheap per-segment speech prob → text only.
        txt = transcribe(audio_path, model_size=model_size)
        return {"text": txt, "no_speech_prob": 0.0, "avg_logprob": 0.0,
                "music_like": False}
    segs = list(model.transcribe(audio_path, **_decode_opts())[0])
    text = " ".join(s.text for s in segs).strip()
    if not segs:
        # VAD found no speech at all → almost certainly background, not you.
        return {"text": text, "no_speech_prob": 1.0, "avg_logprob": -5.0,
                "music_like": True}
    nsp = sum(getattr(s, "no_speech_prob", 0.0) for s in segs) / len(segs)
    alp = sum(getattr(s, "avg_logprob", 0.0) for s in segs) / len(segs)
    # SECOND PASS when she's unsure: a SHORT utterance that's clearly speech (low
    # no-speech prob) but decoded shakily (low avg_logprob) is the "few words she
    # doesn't understand" case. Re-decode ONCE harder — wider beam + no VAD (so a
    # brief clip isn't trimmed) — and keep it only if it's more confident. Cheap:
    # only fires on the rare shaky-short clip, not normal turns.
    import os as _os
    if (len(text) < 24 and nsp < 0.4 and alp < -0.85
            and _os.environ.get("CTWIN_STT_SECOND_PASS", "1") != "0"):
        try:
            opts2 = _decode_opts()
            opts2["beam_size"] = max(opts2.get("beam_size", 5), 8)
            opts2["vad_filter"] = False               # don't trim a short clip
            opts2["temperature"] = [0.0, 0.2, 0.4, 0.6, 0.8]
            segs2 = list(model.transcribe(audio_path, **opts2)[0])
            if segs2:
                alp2 = sum(getattr(s, "avg_logprob", 0.0) for s in segs2) / len(segs2)
                text2 = " ".join(s.text for s in segs2).strip()
                if text2 and alp2 > alp:              # genuinely more confident
                    segs, text, alp = segs2, text2, alp2
                    nsp = sum(getattr(s, "no_speech_prob", 0.0) for s in segs2) / len(segs2)
        except Exception:
            pass
    # no_speech_prob is the TRUSTWORTHY music/noise signal — real speech (even a
    # mis-decoded short phrase like "Hey Vera"→"Tevira") sits at 0.01–0.07, while
    # music/silence spikes it high. avg_logprob is NOT reliable here: genuine short
    # or unusual words dip to −1.0, so gating on it was eating real "few words".
    # Only call it music when the model itself is fairly sure there's no speech,
    # OR the text collapsed to almost nothing with a high no-speech prob.
    music_like = (nsp >= 0.6) or (nsp >= 0.4 and len(text) < 2)
    return {"text": text, "no_speech_prob": round(nsp, 3),
            "avg_logprob": round(alp, 3), "music_like": music_like}


def status() -> str:
    """One-line human status for diagnostics."""
    b = _which_backend()
    if b:
        return f"local STT ready ({b})"
    return "local STT not installed — browser speech will be used (pip install faster-whisper)"


if __name__ == "__main__":
    print(status())
    if len(sys.argv) > 1 and is_available():
        print(transcribe(sys.argv[1]))
