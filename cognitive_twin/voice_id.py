"""
voice_id — Vera learns YOUR voice, so she knows you from everyone else.

Her mic hears whatever's in the room: you, other people, the television. Without a
sense of *whose* voice it is, a stray sound can be transcribed and acted on as if
you said it (that's how a mis-heard "die" once became a task). This gives her a
voiceprint of you: enroll a few seconds of your speech once, and from then on she
can tell "that was you" from "that was someone else" — and only trust your voice
for tasks and commands.

How it works, kept honest + dependency-light (numpy + stdlib only — the "runs on a
bare Python" rule):
  • A voice is turned into a small EMBEDDING from log-mel / cepstral features
    (a pure-numpy MFCC-style summary of the voice's timbre), averaged over the clip.
  • Enrolling stores the mean embedding of your samples (sealed on-device).
  • A new clip is scored by cosine similarity to your print → a 0..1 confidence
    it's you, with an honest threshold. Below it: "not clearly you" — she holds back
    from treating it as a command, rather than guessing.

Never certainty, always confidence. No audio is stored — only the small, sealed
embedding. Opt-in; off until you enroll.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import io
import math
import wave
from typing import Any

try:
    import numpy as _np
except Exception:                       # pragma: no cover
    _np = None

from . import security

_STORE = "voice_id.json"                # the sealed voiceprint (mean embedding)
_N_MELS = 24                            # mel bands → embedding dimensionality
_FRAME = 400                            # ~25ms at 16k
_HOP = 160                              # ~10ms
# "it's you" threshold on cosine similarity. Tuned conservative: better to ask
# "was that you?" than to act on someone else. Adjustable via CTWIN_VOICEID_THRESH.
_DEFAULT_THRESH = 0.72


# ── WAV → mono float samples (stdlib, any-rate) ───────────────────────────────
def _read_wav(data: bytes) -> tuple["_np.ndarray | None", int]:
    if _np is None:
        return None, 0
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            n, sr, ch, sw = w.getnframes(), w.getframerate(), w.getnchannels(), w.getsampwidth()
            raw = w.readframes(n)
        if sw == 2:
            x = _np.frombuffer(raw, dtype=_np.int16).astype(_np.float32) / 32768.0
        elif sw == 1:
            x = (_np.frombuffer(raw, dtype=_np.uint8).astype(_np.float32) - 128.0) / 128.0
        else:
            x = _np.frombuffer(raw, dtype=_np.int16).astype(_np.float32) / 32768.0
        if ch > 1:
            x = x.reshape(-1, ch).mean(axis=1)
        return x, sr
    except Exception:
        return None, 0


# ── a small, pure-numpy voice embedding (MFCC-ish timbre summary) ──────────────
def _mel_filterbank(n_fft: int, sr: int, n_mels: int):
    def hz_to_mel(f): return 2595.0 * _np.log10(1.0 + f / 700.0)
    def mel_to_hz(m): return 700.0 * (10 ** (m / 2595.0) - 1.0)
    lo, hi = hz_to_mel(80.0), hz_to_mel(min(7600.0, sr / 2))
    pts = mel_to_hz(_np.linspace(lo, hi, n_mels + 2))
    bins = _np.floor((n_fft + 1) * pts / sr).astype(int)
    fb = _np.zeros((n_mels, n_fft // 2 + 1), dtype=_np.float32)
    for m in range(1, n_mels + 1):
        l, c, r = bins[m - 1], bins[m], bins[m + 1]
        for k in range(l, c):
            if c > l: fb[m - 1, k] = (k - l) / (c - l)
        for k in range(c, r):
            if r > c: fb[m - 1, k] = (r - k) / (r - c)
    return fb


def embed(wav_bytes: bytes) -> list[float]:
    """Turn a WAV clip into a small voice embedding (timbre fingerprint). Returns
    [] when numpy is absent or the clip is too short/silent to characterize."""
    if _np is None:
        return []
    x, sr = _read_wav(wav_bytes)
    if x is None or len(x) < _FRAME * 3:
        return []
    # pre-emphasis + framing
    x = _np.append(x[0], x[1:] - 0.97 * x[:-1])
    n_fft = 512
    win = _np.hanning(_FRAME).astype(_np.float32)
    frames = []
    for start in range(0, len(x) - _FRAME, _HOP):
        frames.append(x[start:start + _FRAME] * win)
    if not frames:
        return []
    F = _np.stack(frames)
    # power spectrum → mel → log → DCT-ish (keep low cepstral coeffs = timbre)
    spec = _np.abs(_np.fft.rfft(F, n=n_fft)) ** 2
    fb = _mel_filterbank(n_fft, sr, _N_MELS)
    mel = _np.maximum(spec @ fb.T, 1e-10)
    logmel = _np.log(mel)
    # drop very quiet frames (silence/noise) so the print is the actual voice
    energy = logmel.mean(axis=1)
    thr = _np.percentile(energy, 40)
    voiced = logmel[energy >= thr]
    if len(voiced) < 3:
        voiced = logmel
    # the embedding: mean + std of each log-mel band over voiced frames (timbre +
    # its spread). L2-normalized so cosine similarity is meaningful.
    emb = _np.concatenate([voiced.mean(axis=0), voiced.std(axis=0)])
    norm = _np.linalg.norm(emb) or 1.0
    return [float(v) for v in (emb / norm)]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    s = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return (s / (na * nb) + 1.0) / 2.0            # map [-1,1] → [0,1]


# ── enrollment (sealed) ───────────────────────────────────────────────────────
def _load() -> dict[str, Any]:
    d = security.read_state(security.path(_STORE), default={})
    return d if isinstance(d, dict) else {}


def is_enrolled() -> bool:
    return bool(_load().get("print"))


def enroll(wav_bytes: bytes) -> str:
    """Add a sample of your voice to your print (rolling mean of the embeddings).
    Call it a few times with a few seconds of your speech each. Returns a status."""
    emb = embed(wav_bytes)
    if not emb:
        return "That clip was too short or quiet to learn your voice from — a few seconds of clear speech works best."
    d = _load()
    cur = d.get("print")
    k = int(d.get("samples", 0))
    if cur and len(cur) == len(emb):
        merged = [(cur[i] * k + emb[i]) / (k + 1) for i in range(len(emb))]
    else:
        merged = emb
    # re-normalize the running mean
    if _np is not None:
        n = _np.linalg.norm(merged) or 1.0
        merged = [float(v) / float(n) for v in merged]
    security.write_state(security.path(_STORE), {"print": merged, "samples": k + 1})
    return f"Learned a bit more of your voice ({k + 1} sample{'s' if k else ''}). The more you enroll, the surer I am it's you."


def clear() -> None:
    security.write_state(security.path(_STORE), {})


def _threshold() -> float:
    import os
    try:
        return float(os.environ.get("CTWIN_VOICEID_THRESH", _DEFAULT_THRESH))
    except ValueError:
        return _DEFAULT_THRESH


# ── the question she asks: was that YOU? ──────────────────────────────────────
def identify(wav_bytes: bytes) -> dict[str, Any]:
    """Is this clip you? Returns {known, is_you, confidence, reason}. When not
    enrolled (or numpy absent), `known` is False and she treats the clip normally —
    this never blocks her; it only ADDS certainty when you've taught her your voice."""
    if not is_enrolled() or _np is None:
        return {"known": False, "is_you": None, "confidence": 0.0,
                "reason": "voice not enrolled — can't tell whose it is yet"}
    emb = embed(wav_bytes)
    if not emb:
        return {"known": True, "is_you": None, "confidence": 0.0,
                "reason": "too short/quiet to tell"}
    sim = _cosine(_load()["print"], emb)
    thr = _threshold()
    return {"known": True, "is_you": sim >= thr, "confidence": round(sim, 3),
            "reason": ("sounds like you" if sim >= thr else "doesn't sound like you")}


def is_you(wav_bytes: bytes) -> bool | None:
    """Convenience: True = you, False = someone else, None = can't tell / not enrolled.
    Callers use `None`/`True` to proceed and `False` to hold back from acting."""
    return identify(wav_bytes).get("is_you")


def status() -> str:
    d = _load()
    if not d.get("print"):
        return ("voice identity: off — I don't know your voice yet. Enroll a few "
                "seconds of your speech so I can tell you from others and the TV.")
    return (f"voice identity: on — learned from {d.get('samples', 1)} sample(s), "
            f"sealed on this device. Threshold {_threshold():.2f}.")
