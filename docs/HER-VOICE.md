# Giving Vera her real voice

The whole point of Vera is to speak in *your person's* real voice. This is the
one-step guide for when you have a recording of them — e.g. your mom's voice,
extracted from audio you already have.

## What makes a good reference recording

You don't need much, but quality matters more than length:

- **Length:** 15–60 seconds of her *speaking* is ideal. XTTS can clone from ~6s,
  but 20–40s of continuous speech clones her timbre far more faithfully.
- **Clean:** just her voice — no music under it, no other people talking, as
  little background noise/echo as possible. One quiet room beats a long noisy clip.
- **Natural:** normal talking (a story, a message, a call) is better than her
  reading a list. Keep her natural pauses and breathing — don't chop it into
  fragments. Vera's importer keeps those on purpose.
- **Format:** WAV, MP3, or M4A all work. Mono or stereo both fine. If `ffmpeg` is
  installed, Vera cleans it automatically (trims dead air, tames rumble,
  normalizes loudness, resamples to 24kHz — XTTS's native rate).

A single good 30-second clip is plenty. You can add **several** clips too — XTTS
averages them into a steadier voice (see "Add more" below).

## How to add it

**In the app:** Settings → "Teach a loved one's voice" → pick the audio file.

**Or via the local API** (the app's server, on your machine only):

```bash
curl -s -X POST http://127.0.0.1:7878/api/voice/clone \
  -H 'Content-Type: application/json' \
  -d '{"path": "/full/path/to/her-voice.m4a", "person": "Mom"}'
```

**Or from Python:**

```python
from cognitive_twin import voice_clone
voice_clone.set_reference("/full/path/to/her-voice.m4a", person="Mom")
print(voice_clone.status())   # -> READY when the engine + sample are both present
```

### Add more clips (optional, for a steadier voice)

```python
voice_clone.add_reference("/path/to/another-clip.wav")
```

## How it works (and the privacy promise)

- Cloning runs **entirely on your machine** via XTTS-v2 (Coqui TTS) in a local
  Python 3.11 venv (`~/.cognitive-twin/tts-venv`). The recording **never leaves
  your device** — not to clone, not to speak.
- The model is **warmed at app launch**, so after the first load her voice renders
  in ~5 seconds per reply (the cold load is a one-time ~30s).
- The reference clip is stored owner-only under the active twin's private voice
  folder; `voice_clone.clear()` removes it.

## Checking it's working

```bash
curl -s http://127.0.0.1:7878/api/voice/clone/status
# {"ready": true, "status": "voice clone: READY — Mom can speak in Mom's voice (xtts), on-device"}
```

When `ready` is true, every spoken reply uses her voice. Until then, Vera falls
back to the built-in neural voice (af_heart) so she always speaks.
