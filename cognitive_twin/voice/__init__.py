"""
Voice layer — a local-first, Siri-style front end for the Cognitive Twin.

Built in the spirit of Unhosted: the work stays on your machine. Text-to-speech
uses macOS `say` (offline, built in); speech-to-text uses local Whisper when it's
installed, and the browser's own speech recognition in the web UI otherwise. Both
feed the same tested agent loop + model router.

Modules:
  tts.py       speak text with macOS `say` (offline)
  stt.py       transcribe audio with local Whisper (optional dependency)
  server.py    localhost HTTP server: serves the Siri web UI + /api/ask
  menubar.py   thin rumps menubar launcher (optional dependency)
  web/         the Siri waveform UI (kopiro/siriwave)
"""

from __future__ import annotations
