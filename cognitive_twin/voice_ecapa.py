"""
voice_ecapa — the BEST on-device voice embedding, when it's available.

The pure-numpy MFCC print in `voice_id` is honest and dependency-free, but it only
summarizes timbre — it can struggle to tell two similar voices apart, especially
with background noise. This module gives Vera a far stronger ear: ECAPA-TDNN, a
real speaker-verification network (the kind used for voice biometrics), run through
a small ONNX file with `onnxruntime` — no PyTorch, still 100% on-device, no cloud.

It's OPTIONAL. If `onnxruntime` or the model file isn't present, `available()` is
False and `voice_id` quietly keeps using its numpy print. Nothing breaks; she just
hears less sharply. To turn it on:

    pip install onnxruntime
    # place an ECAPA-TDNN ONNX at one of the paths in _MODEL_PATHS (see below),
    # e.g. exported from speechbrain/spkrec-ecapa-voxceleb (192-dim embedding).

The model is loaded once and reused. Input: 16 kHz mono WAV bytes. Output: a
192-dim L2-normalized embedding (list[float]) — same contract as voice_id.embed,
so the two are drop-in interchangeable.

© Ankur Sinha. Personal use.
"""

from __future__ import annotations

import io
import os
import wave

try:
    import numpy as _np
except Exception:                       # pragma: no cover
    _np = None

try:
    import onnxruntime as _ort          # optional — the whole point is graceful absence
except Exception:                       # pragma: no cover
    _ort = None

# Where we look for the ONNX model, in order. Keep it on-device + discoverable.
# CTWIN_ECAPA_MODEL wins; then the sealed model dir; then a repo-local models/ dir.
_MODEL_PATHS = [
    os.environ.get("CTWIN_ECAPA_MODEL", ""),
    os.path.expanduser("~/.cognitive-twin/models/ecapa.onnx"),
    os.path.join(os.path.dirname(__file__), "..", "models", "ecapa.onnx"),
]

_SESSION = None                         # cached onnxruntime.InferenceSession
_LOADED = False                         # have we tried (so we don't retry every call)
_INPUT_NAME: str | None = None


def model_path() -> str | None:
    """The first ECAPA ONNX that actually exists on disk, or None."""
    for p in _MODEL_PATHS:
        if p and os.path.isfile(p):
            return os.path.abspath(p)
    return None


def available() -> bool:
    """True only when numpy + onnxruntime + a real model file are all present."""
    return _np is not None and _ort is not None and model_path() is not None


def _session():
    """Load the ONNX model once (CPU provider — small, fast, no GPU needed)."""
    global _SESSION, _LOADED, _INPUT_NAME
    if _LOADED:
        return _SESSION
    _LOADED = True
    p = model_path()
    if not p or _ort is None:
        return None
    try:
        opts = _ort.SessionOptions()
        opts.intra_op_num_threads = max(1, (os.cpu_count() or 2) // 2)
        _SESSION = _ort.InferenceSession(p, sess_options=opts,
                                         providers=["CPUExecutionProvider"])
        _INPUT_NAME = _SESSION.get_inputs()[0].name
    except Exception:
        _SESSION = None
    return _SESSION


def _read_wav_16k(data: bytes):
    """WAV bytes → mono float32 at 16 kHz (linear resample). None if unreadable."""
    if _np is None:
        return None
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
        if sr != 16_000 and len(x):
            ratio = sr / 16_000.0
            out_n = int(len(x) / ratio)
            idx = (_np.arange(out_n) * ratio)
            lo = idx.astype(int)
            frac = (idx - lo).astype(_np.float32)
            lo = _np.clip(lo, 0, len(x) - 1)
            hi = _np.clip(lo + 1, 0, len(x) - 1)
            x = x[lo] * (1 - frac) + x[hi] * frac
        return x.astype(_np.float32)
    except Exception:
        return None


def embed(wav_bytes: bytes) -> list[float]:
    """Turn a WAV clip into a 192-dim ECAPA speaker embedding (L2-normalized).

    Returns [] when the model isn't available or the clip is too short/quiet —
    the caller (voice_id) then falls back to its numpy print. Never raises on a
    bad clip; a stray noise just yields []."""
    sess = _session()
    if sess is None or _np is None:
        return []
    x = _read_wav_16k(wav_bytes)
    if x is None or len(x) < 16_000 * 0.4:      # need ~0.4s of audio minimum
        return []
    # ECAPA expects a batch of raw waveforms: shape (1, samples), float32.
    feats = x.reshape(1, -1).astype(_np.float32)
    try:
        out = sess.run(None, {_INPUT_NAME: feats})[0]
    except Exception:
        return []
    emb = _np.asarray(out, dtype=_np.float32).reshape(-1)
    if emb.size == 0:
        return []
    norm = float(_np.linalg.norm(emb)) or 1.0
    return [float(v) for v in (emb / norm)]


def kind() -> str:
    """Which embedder is active — used to tag a print so we never cross-compare."""
    return "ecapa-onnx" if available() else "none"
