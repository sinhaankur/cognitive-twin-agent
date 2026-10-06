"""
Piper — a natural, on-device NEURAL voice for Vera.

macOS `say` sounds robotic unless you've downloaded Apple's Premium voices. Piper
is a small neural TTS (ONNX) that sounds genuinely human and ships WITH Vera, so
she has a warm voice on every machine with no system download.

Architecture: the brain runs as a BACKGROUND service, which macOS won't let play
audio — but it CAN compute. So this module only SYNTHESIZES a WAV (pure CPU work);
the app plays it (GUI context). The server exposes the WAV at /api/voice/piper.

Everything is local: the piper venv + the voice model live under VERA_HOME
(``~/Library/Application Support/Vera``). No cloud, no license issues (Piper is
MIT; the lessac voice is public-domain/MIT).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _vera_home() -> Path:
    return Path(os.environ.get("VERA_HOME",
               Path.home() / "Library" / "Application Support" / "Vera"))


def _piper_bin() -> str | None:
    """The piper executable from Vera's dedicated venv (or PATH as a fallback)."""
    cand = _vera_home() / "piper-venv" / "bin" / "piper"
    if cand.is_file() and os.access(cand, os.X_OK):
        return str(cand)
    return shutil.which("piper")


def _voice_model() -> Path | None:
    """The chosen Piper voice model (.onnx). Defaults to the warm lessac voice;
    override with CTWIN_PIPER_VOICE (a model name under VERA_HOME/voices)."""
    voices = _vera_home() / "voices"
    # Default = Kristin (en_US-kristin): a gentle, warm, distinctly feminine voice.
    # A feminine, unhurried voice sets the companion tone — it makes the exchange
    # feel like there's time (the "Her" feeling). Override with CTWIN_PIPER_VOICE.
    name = os.environ.get("CTWIN_PIPER_VOICE", "en_US-kristin-medium")
    model = voices / f"{name}.onnx"
    if model.is_file():
        return model
    # fall back to any installed .onnx so a differently-named voice still works
    if voices.is_dir():
        for m in sorted(voices.glob("*.onnx")):
            return m
    return None


def is_available() -> bool:
    """True when the piper binary AND a voice model are both present."""
    return _piper_bin() is not None and _voice_model() is not None


# Friendly labels for the feminine voices Vera ships, so the picker reads nicely.
_VOICE_LABELS = {
    "en_US-kristin-medium":     "Kristin — gentle US female",
    "en_GB-cori-high":          "Cori — soft British (high quality)",
    "en_US-hfc_female-medium":  "Clara — clear US female",
    "en_US-kathleen-low":       "Kathleen — low, calm US female",
    "en_GB-jenny_dioco-medium": "Jenny — soft British female",
    "en_US-amy-medium":         "Amy — warm US female",
    "en_US-lessac-medium":      "Lessac — neutral US",
}


def list_voices() -> list[dict[str, str]]:
    """Installed Piper voices (id + friendly label) + which one is current."""
    voices = _vera_home() / "voices"
    out: list[dict[str, str]] = []
    if voices.is_dir():
        for m in sorted(voices.glob("*.onnx")):
            vid = m.stem
            out.append({"id": vid, "label": _VOICE_LABELS.get(vid, vid)})
    return out


def current_voice() -> str:
    m = _voice_model()
    return m.stem if m else ""


def set_voice(voice_id: str) -> bool:
    """Choose the active Piper voice (by model id). Takes effect immediately for
    this process; the app persists the choice and re-sends it on launch."""
    voice_id = (voice_id or "").strip()
    if not voice_id:
        return False
    model = _vera_home() / "voices" / f"{voice_id}.onnx"
    if not model.is_file():
        return False
    os.environ["CTWIN_PIPER_VOICE"] = voice_id
    return True


def status() -> str:
    if is_available():
        return f"piper ready ({_voice_model().name})"  # type: ignore[union-attr]
    if _piper_bin() is None:
        return "piper not installed"
    return "piper installed, no voice model"


def synth_wav(text: str, *, length_scale: float = 1.0) -> bytes | None:
    """Synthesize `text` to WAV bytes with Piper. Returns None if unavailable or
    on error (the caller falls back to the system voice). length_scale > 1 is
    slower/warmer; < 1 is quicker.

    A touch slower than default reads as calmer and more human — fitting for Vera.
    """
    text = (text or "").strip()
    if not text:
        return None
    binp = _piper_bin()
    model = _voice_model()
    if not binp or not model:
        return None
    try:
        proc = subprocess.run(
            [binp, "-m", str(model), "-f", "-",            # -f - → WAV to stdout
             "--length-scale", f"{max(0.5, min(2.0, length_scale)):.2f}"],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0 or not proc.stdout:
            return None
        # stdout is a complete WAV (RIFF header + PCM). Sanity-check the header.
        if proc.stdout[:4] != b"RIFF":
            return None
        return proc.stdout
    except (OSError, subprocess.SubprocessError):
        return None
