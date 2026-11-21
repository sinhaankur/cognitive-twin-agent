"""
voice_id — Vera learns YOUR voice, so she knows you from everyone else.

Her mic hears whatever's in the room: you, other people, the television. Without a
sense of *whose* voice it is, a stray sound can be transcribed and acted on as if
you said it (that's how a mis-heard "die" once became a task). This gives her a
voiceprint of you: enroll a few seconds of your speech once, and from then on she
can tell "that was you" from "that was someone else" — and only trust your voice
for tasks and commands.

How it works, kept honest + dependency-light:
  • A voice is turned into a small EMBEDDING. By default that's a pure-numpy
    MFCC-style timbre summary (the "runs on a bare Python" rule). If the optional
    ECAPA-TDNN ONNX model is present (see `voice_ecapa`), she uses that instead —
    real speaker-verification embeddings, noise-robust, still 100% on-device.
  • ONBOARDING YOU vs. SOMEONE ELSE. Enrolling stores the mean of your samples as
    your print. But knowing *you* isn't enough to know *not-you* — so she also keeps
    a small "others" gallery: voices she's confidently decided weren't you. A new
    clip is then judged RELATIVELY — is it closer to your print, or closer to the
    strangers she's heard? That boundary is where "it's you" really lives.
  • HUMAN LEARNING. Every clip she's sure is you quietly strengthens your print
    (rolling mean) and widens your "spread", so you become a region, not one point.
    Every clip she's sure isn't you seeds the others gallery. She gets surer of you
    the more you talk — like a person learning your voice over weeks.

Scoring: cosine similarity to your print → a 0..1 confidence, with an honest
margin over the nearest stranger. Below it: "not clearly you" — she holds back
from treating it as a command, rather than guessing.

Never certainty, always confidence. No audio is stored — only the small, sealed
embeddings. Opt-in; off until you enroll.

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


def active_kind() -> str:
    """Which embedder is in play: 'ecapa-onnx' (best, optional) or 'mfcc' (always).
    A stored print records this so we never cross-compare incompatible embeddings."""
    try:
        from . import voice_ecapa
        if voice_ecapa.available():
            return "ecapa-onnx"
    except Exception:
        pass
    return "mfcc"


def embed(wav_bytes: bytes) -> list[float]:
    """Turn a WAV clip into a voice embedding (fingerprint). Uses ECAPA-TDNN when
    the optional ONNX model is present (best, noise-robust), else the pure-numpy
    MFCC timbre print. Returns [] when numpy is absent or the clip is too short."""
    try:
        from . import voice_ecapa
        if voice_ecapa.available():
            e = voice_ecapa.embed(wav_bytes)
            if e:
                return e
            # ECAPA present but clip unusable → don't silently fall back to a
            # different embedding space; just return []. (Same-space contract.)
            return []
    except Exception:
        pass
    return _embed_mfcc(wav_bytes)


def _embed_mfcc(wav_bytes: bytes) -> list[float]:
    """The pure-numpy timbre print (the always-available fallback embedder)."""
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


# ── sealed store: your print + the "others" gallery + which embedder made them ──
#
# Shape:
#   { "kind": "mfcc" | "ecapa-onnx",       # embedder that produced these vectors
#     "print": [...], "samples": N,        # YOU — rolling-mean embedding
#     "spread": float,                     # how much your voice varies (self-sim std)
#     "others": [[...], ...] }             # NOT-YOU gallery (recent strangers, capped)
_MAX_OTHERS = 12                            # keep the gallery small + recent
_MARGIN = 0.04                              # you must beat the nearest stranger by this


def _load() -> dict[str, Any]:
    d = security.read_state(security.path(_STORE), default={})
    return d if isinstance(d, dict) else {}


def _save(d: dict[str, Any]) -> None:
    security.write_state(security.path(_STORE), d)


def is_enrolled() -> bool:
    return bool(_load().get("print"))


def _l2(v: list[float]) -> list[float]:
    if _np is None or not v:
        return v
    n = float(_np.linalg.norm(v)) or 1.0
    return [float(x) / n for x in v]


def _fresh_if_kind_changed(d: dict[str, Any]) -> dict[str, Any]:
    """If the active embedder differs from the one that built the stored print, the
    vectors live in a different space and can't be compared — start that store clean.
    (This happens the day you install/remove the ECAPA model; honest, not silent.)"""
    cur = active_kind()
    if d.get("print") and d.get("kind") and d.get("kind") != cur:
        return {"kind": cur, "pending_rekind": d.get("kind")}
    if not d.get("kind"):
        d["kind"] = cur
    return d


def enroll(wav_bytes: bytes) -> str:
    """Add a sample of YOUR voice to your print (rolling mean). Call it a few times
    with a few seconds of clear speech. This is onboarding: it teaches 'you'."""
    emb = embed(wav_bytes)
    if not emb:
        return ("That clip was too short or quiet to learn your voice from — a few "
                "seconds of clear, close speech works best.")
    d = _fresh_if_kind_changed(_load())
    cur = d.get("print")
    k = int(d.get("samples", 0))
    if cur and len(cur) == len(emb):
        merged = _l2([(cur[i] * k + emb[i]) / (k + 1) for i in range(len(emb))])
        # track how much YOU vary from your own mean — your natural spread
        self_sim = _cosine(merged, emb)
        prev = float(d.get("spread", 0.0))
        spread = prev * 0.7 + (1.0 - self_sim) * 0.3
    else:
        merged, spread = emb, 0.0
    d.update({"kind": active_kind(), "print": merged, "samples": k + 1,
              "spread": round(spread, 4)})
    d.pop("pending_rekind", None)
    _save(d)
    extra = "" if k else " I'll get surer every time you talk to me."
    return (f"Learned a bit more of your voice ({k + 1} sample"
            f"{'s' if k else ''}).{extra}")


def note_other(wav_bytes: bytes) -> None:
    """Remember that THIS clip wasn't you — seed the 'others' gallery so the line
    between you and everyone else sharpens. Called when she's confident it's a
    stranger. Capped + recency-pruned; stores only the embedding, never audio."""
    if not is_enrolled():
        return
    emb = embed(wav_bytes)
    if not emb:
        return
    d = _fresh_if_kind_changed(_load())
    others = [o for o in d.get("others", []) if isinstance(o, list) and len(o) == len(emb)]
    # skip near-duplicates so the gallery stays diverse, not N copies of the TV
    if any(_cosine(o, emb) > 0.985 for o in others):
        return
    others.append(emb)
    d["others"] = others[-_MAX_OTHERS:]
    _save(d)


def learn_you(wav_bytes: bytes) -> None:
    """Human learning: a clip she's SURE is you → quietly fold it into your print,
    so she recognizes you better over time. Same math as enroll, but silent and
    self-triggered from confident turns (never from a shaky guess)."""
    enroll(wav_bytes)


def clear() -> None:
    _save({})


def _threshold() -> float:
    import os
    try:
        return float(os.environ.get("CTWIN_VOICEID_THRESH", _DEFAULT_THRESH))
    except ValueError:
        return _DEFAULT_THRESH


# ── the question she asks: was that YOU, or someone else? ─────────────────────
def identify(wav_bytes: bytes) -> dict[str, Any]:
    """Is this clip you? Returns {known, is_you, confidence, reason, you_sim,
    other_sim}. When not enrolled (or numpy absent), `known` is False and she
    treats the clip normally — this never blocks her; it only ADDS certainty.

    Decision = RELATIVE when she's heard strangers: it's you only if the clip is
    both (a) above the absolute threshold AND (b) closer to your print than to the
    nearest stranger by a clear margin. With no strangers yet, it's the threshold
    alone (widened a touch by your own measured spread, so a yawn/whisper of yours
    isn't mistaken for not-you)."""
    if not is_enrolled() or _np is None:
        return {"known": False, "is_you": None, "confidence": 0.0,
                "reason": "voice not enrolled — can't tell whose it is yet"}
    emb = embed(wav_bytes)
    if not emb:
        return {"known": True, "is_you": None, "confidence": 0.0,
                "reason": "too short/quiet to tell"}
    d = _load()
    you_sim = _cosine(d["print"], emb)
    others = d.get("others", [])
    other_sim = max((_cosine(o, emb) for o in others
                     if isinstance(o, list) and len(o) == len(emb)), default=0.0)
    # widen "you" by your natural spread so your own off-days still read as you
    thr = max(0.5, _threshold() - float(d.get("spread", 0.0)))
    above = you_sim >= thr
    # The "others" gallery breaks TIES near the boundary — it must never veto a clip
    # that clearly matches your print. So: if you're strongly above threshold, you're
    # you even when a stranger scores close (coarse ears make voices look alike). The
    # relative margin only bites in the ambiguous band just above the threshold.
    strong = you_sim >= (thr + 0.12)
    beats_others = (not others) or strong or (you_sim >= other_sim + _MARGIN)
    is_you_ = bool(above and beats_others)
    if not above:
        reason = "doesn't sound like you"
    elif not beats_others:
        reason = "sounds closer to someone else she's heard"
    else:
        reason = "sounds like you"
    return {"known": True, "is_you": is_you_, "confidence": round(you_sim, 3),
            "you_sim": round(you_sim, 3), "other_sim": round(other_sim, 3),
            "reason": reason}


def is_you(wav_bytes: bytes) -> bool | None:
    """Convenience: True = you, False = someone else, None = can't tell / not enrolled.
    Callers use `None`/`True` to proceed and `False` to hold back from acting."""
    return identify(wav_bytes).get("is_you")


def status() -> str:
    d = _load()
    if not d.get("print"):
        return ("voice identity: off — I don't know your voice yet. Enroll a few "
                "seconds of your speech so I can tell you from others and the TV.")
    k = active_kind()
    ear = "ECAPA (best)" if k == "ecapa-onnx" else "numpy timbre print"
    others = len(d.get("others", []))
    gal = f", {others} other voice{'s' if others != 1 else ''} to contrast against" if others else ""
    return (f"voice identity: on — learned from {d.get('samples', 1)} sample(s){gal}, "
            f"sealed on this device. Ear: {ear}. Threshold {_threshold():.2f}.")
