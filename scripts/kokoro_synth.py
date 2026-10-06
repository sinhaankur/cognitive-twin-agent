#!/usr/bin/env python3
"""Kokoro synth worker — reads lines of JSON {text, voice, speed} on stdin,
writes a WAV path per request on stdout. Model loads ONCE and stays warm, so
each reply is fast. Pure on-device (Kokoro-82M). Used by cognitive_twin."""
import sys, json, os, tempfile
import soundfile as sf
from kokoro import KPipeline

_pipe = KPipeline(lang_code='a')  # American English (handles af_/am_ voices)

def synth(text, voice, speed):
    audio = None
    for _, _, aud in _pipe(text, voice=voice, speed=speed):
        audio = aud if audio is None else audio  # first chunk
        break
    f = tempfile.NamedTemporaryFile(suffix='.wav', delete=False, dir='/tmp')
    sf.write(f.name, audio, 24000)
    return f.name

print("READY", flush=True)
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
        path = synth(req.get("text",""), req.get("voice","af_bella"),
                     float(req.get("speed", 0.92)))
        print(json.dumps({"wav": path}), flush=True)
    except Exception as e:
        print(json.dumps({"error": str(e)}), flush=True)
