"""
Local voice server — the bridge between the Siri web UI and the agent.

A tiny stdlib HTTP server bound to 127.0.0.1 (never exposed off the machine).
It serves the Siri waveform UI and a small JSON API:

  GET  /                  the Siri web UI
  GET  /api/health        { ok, stt, tts, model }
  POST /api/ask           { "text": "..." } -> { "answer": "...", "route": {...} }
  POST /api/council       { "text": "...", "twins"?: [..] } -> { "takes": [{name, answer, model, error}] }
  POST /api/speak         { "text": "..." } -> speaks via macOS `say`, { "ok": true }

The agent + model router are the ones already built and tested. Speech-to-text in
this path is the browser's job (Web Speech API); /api/speak handles talk-back with
local `say`. Local Whisper is available via the CLI/menubar path.

Run:  python -m cognitive_twin.voice.server
"""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import tts
from . import stt
from .. import control
from ..cli import build_agent, _run_once_capture  # agent wiring (see cli.py)


# In the voice path there's no y/N dialog yet, so mutating screen actions are
# auto-denied unless the user opts into auto-confirm (CTWIN_CONTROL_AUTOCONFIRM=1).
# Read actions ("see the screen") are always allowed when control is enabled.
def _voice_confirm(action: str) -> bool:
    import os as _os
    return _os.environ.get("CTWIN_CONTROL_AUTOCONFIRM", "").strip() in {"1", "true", "yes"}


control.set_confirm(_voice_confirm)


# Track the current server-side playback so a barge-in / stop can silence it.
_playback_lock = threading.Lock()
_playback_proc: Any = None


def _play_wav_bytes(wav: bytes) -> None:
    """Play WAV bytes on this machine via macOS `afplay`, fire-and-forget so the
    HTTP handler returns immediately. Any prior playback is stopped first so she
    never doubles up. On-device, no network."""
    import os as _os
    import subprocess as _sp
    import tempfile as _tf
    global _playback_proc
    f = _tf.NamedTemporaryFile(suffix=".wav", delete=False, dir="/tmp")
    try:
        f.write(wav)
        f.flush()
        f.close()
        with _playback_lock:
            if _playback_proc and _playback_proc.poll() is None:
                try:
                    _playback_proc.kill()
                except OSError:
                    pass
            _playback_proc = _sp.Popen(
                ["/usr/bin/afplay", f.name],
                stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
            )
        proc = _playback_proc

        def _cleanup(p, path):
            try:
                p.wait()
            except Exception:
                pass
            try:
                _os.unlink(path)
            except OSError:
                pass
        threading.Thread(target=_cleanup, args=(proc, f.name), daemon=True).start()
    except Exception:
        try:
            _os.unlink(f.name)
        except OSError:
            pass


WEB_DIR = Path(__file__).resolve().parent / "web"
HOST = "127.0.0.1"
DEFAULT_PORT = 7878


def _llm_error_message(e: Exception) -> str:
    """Turn a raw LLM failure into a warm, actionable line — never a cryptic
    '(error: ...)'. Vera must never look broken: if the model is unreachable or
    none is installed, she says so plainly and tells the user the one step to fix
    it. The agent already auto-falls-back to any installed model (incl. the tiny
    companion), so reaching here means Ollama is down or nothing is pulled."""
    msg = str(e).lower()
    if "isn't running" in msg or "unreachable" in msg or "connection" in msg or "refused" in msg:
        return ("I can't reach the local model right now. Start Ollama (open the "
                "Ollama app, or run `ollama serve`) and I'll be right back — "
                "everything stays on your machine.")
    if "isn't pulled" in msg or "not found" in msg or "no model" in msg or "install" in msg:
        return ("I don't have a model to think with yet. Pull a small one with "
                "`ollama pull qwen2.5:3b` (or `empathia-tiny-opt`) and I'll use it — "
                "all on-device.")
    # unknown hiccup — stay honest but not scary
    return f"I hit a snag reaching the model ({e}). It's usually Ollama not running yet."

# True while the opt-in "See a loved one in 3D" build (depth + Blender) runs on a
# worker thread, so /api/portrait/status can report progress. See portrait.py.
_portrait_building = False


class _Handler(BaseHTTPRequestHandler):
    # the shared agent is attached to the server instance
    def _allow_origin(self) -> str:
        """Which origin to echo back for CORS. Same-origin (the app's own web
        UI) always; PLUS browser extensions (chrome-/moz-extension://…), so the
        Vera browser extension can POST a logged-in mail tab to the local core.
        No password ever transits — only the messages the page already shows."""
        own = "http://%s:%d" % (HOST, self.server.server_address[1])
        origin = self.headers.get("Origin", "")
        if origin.startswith(("chrome-extension://", "moz-extension://", "safari-web-extension://")):
            return origin
        return own

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # local-only app; allow the page's fetch calls + the Vera extension
        self.send_header("Access-Control-Allow-Origin", self._allow_origin())
        self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        # CORS preflight for the browser extension's POST.
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self._allow_origin())
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def _json(self, code: int, obj: dict[str, Any]) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def log_message(self, *args: Any) -> None:  # quiet by default
        pass

    def _cloned_ready(self) -> bool:
        try:
            from .. import voice_clone
            return voice_clone.is_ready()
        except Exception:
            return False

    # ---- routes -------------------------------------------------------------
    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._serve_file("index.html", "text/html; charset=utf-8")
        elif self.path == "/siriwave.js":
            self._serve_file("siriwave.js", "application/javascript; charset=utf-8")
        elif self.path == "/app.js":
            self._serve_file("app.js", "application/javascript; charset=utf-8")
        elif self.path == "/flow.js":
            self._serve_file("flow.js", "application/javascript; charset=utf-8")
        elif self.path.split("?")[0] in ("/mind", "/mind.html"):
            # The Mind — a calm, legible animated pipeline (question → retrieve →
            # feel → answer). Replaces the noisy galaxy; everything in the app.
            # (split on ? so a seed like /mind?q=… still serves the page.)
            self._serve_file("mind.html", "text/html; charset=utf-8")
        elif self.path == "/eye":
            # the app's small preview window (see eye.html header note)
            self._serve_file("eye.html", "text/html; charset=utf-8")
        elif self.path in ("/controls", "/controls.html"):
            # the automation control panel (switches for every data source +
            # capability + the booker). All logic lives in controls.py — this
            # page is just a front-end over it.
            self._serve_file("controls.html", "text/html; charset=utf-8")
        elif self.path == "/api/controls":
            from .. import controls
            self._json(200, {"controls": controls.snapshot()})
        elif self.path == "/api/health":
            agent = self.server.agent  # type: ignore[attr-defined]
            # Report the CONFIGURED default (stable), not agent.client.model — with
            # routing on, the router rewrites client.model per request, so reading it
            # here showed whatever the last turn happened to use (misleading). When
            # routing is active the actual model varies per turn by design; the app
            # can read `routing` to reflect that.
            routing = getattr(agent, "router", None) is not None
            model = getattr(agent, "configured_model", None) or getattr(agent.client, "model", None)
            from . import piper_tts, kokoro_tts
            self._json(200, {
                "ok": True,
                "tts": tts.is_available(),
                "stt_local": stt.is_available(),
                "model": model,
                "routing": routing,
                # Vera's bundled neural voice (Kokoro preferred, Piper fallback) —
                # the app uses it when present for a natural, human-sounding reply.
                # Key kept as "piper" for app compatibility.
                "piper": kokoro_tts.is_available() or piper_tts.is_available(),
                "neural_voice": ("kokoro" if kokoro_tts.is_available()
                                 else "piper" if piper_tts.is_available() else ""),
            })
        elif self.path == "/api/lockdown":
            # Kill-switch status: is Vera dormant (halted from reaching out/acting)?
            from .. import security
            self._json(200, {"locked": security.is_locked()})
            return
        elif self.path == "/api/models":
            agent = self.server.agent  # type: ignore[attr-defined]
            backend = getattr(agent, "backend", None)
            if backend is not None:
                # merged, provider-tagged list across Ollama + OpenAI backends
                models = backend.list_models()
            elif hasattr(agent.client, "available_models"):
                models = agent.client.available_models()
            else:
                models = []
            self._json(200, {"models": models})
        elif self.path == "/api/greet":
            # the greeting as FACT: real clock, real weather, straight from the
            # skill — never via the model, which will happily invent September
            # 2023 and a gentle breeze when it skips the tool
            from ..skills import builtin
            try:
                self._json(200, {"text": builtin.greeting()})
            except Exception as e:
                self._json(200, {"text": "", "error": str(e)})
        elif self.path == "/api/nudge":
            # A gentle, FACTUAL opening nudge for the greeting: one real open task,
            # straight from the local day-shadow — never the model (which invents
            # tasks/events that don't exist, like a 'Super Club event'). Empty when
            # there's genuinely nothing, so the greeting stays just a warm hello.
            try:
                from .. import shadow
                tasks = shadow.open_tasks()
                if tasks:
                    more = f" (and {len(tasks) - 1} more)" if len(tasks) > 1 else ""
                    self._json(200, {"text": f"Still on your plate: {tasks[0].text}{more}."})
                else:
                    self._json(200, {"text": ""})
            except Exception:
                self._json(200, {"text": ""})
        elif self.path == "/api/reflections":
            # thoughts Anita had about your projects while you were away —
            # served ONCE (cleared on delivery): a thought shared twice is a
            # rerun, and reruns are why the default conversation felt old
            from .. import soul
            items = soul.pending_reflections(clear=True)
            self._json(200, {"items": items, "soul": soul.status()})
        elif self.path == "/api/brain" or self.path.startswith("/api/brain?"):
            # A graph snapshot of how the twin thinks + learns (local state only).
            from .. import brain
            from urllib.parse import urlparse, parse_qs
            data = brain.snapshot()
            q = parse_qs(urlparse(self.path).query)
            prompt = (q.get("prompt", [""])[0] or "").strip()
            if prompt:
                data["thought_path"] = brain.thought_path(prompt)
            self._json(200, data)
        elif self.path == "/api/health/activity":
            # Vera's health/activity summary (from an Apple Health export, opt-in).
            # NB: distinct from /api/health (the server liveness check).
            from .. import health as _health
            self._json(200, {"enabled": _health.is_enabled(),
                             "summary": _health.load(),
                             "status": _health.status()})
        elif self.path == "/api/persona":
            # WHO she is right now — the editable persona name + a short bio. The
            # app's Settings reads this so the user can switch/rename her (Anita →
            # Emma, or anything). The name flows into the system prompt, so changing
            # it actually changes who the LLM speaks as.
            from .. import persona as _persona
            p = _persona.load()
            self._json(200, {"name": p.name, "about": p.about, "traits": p.traits})
        elif self.path == "/api/personality":
            # The current personality dials (warmth / humor / playfulness).
            from .. import personality
            self._json(200, {"dials": personality.load()})
        elif self.path == "/api/voices":
            # Her NEURAL (Kokoro) voices — the ones the user actually chooses from
            # ("we had the voice options, why isn't there one"). These are what make
            # her sound human; the macOS `say` voices are only the fallback. Return
            # the Kokoro catalogue + the current selection so Settings can show the
            # real picker. Falls back to system voices only if Kokoro isn't present.
            from . import kokoro_tts
            if kokoro_tts.is_available():
                self._json(200, {
                    "engine": "kokoro",
                    "voices": kokoro_tts.list_voices(),      # [{id,label}, …]
                    "current": kokoro_tts.current_voice(),
                })
            else:
                self._json(200, {
                    "engine": "system",
                    "voices": [{"id": v, "label": v} for v in tts.voices()],
                    "current": tts.best_voice() or "",
                })
        elif self.path == "/api/voice/clone/status":
            from .. import voice_clone
            self._json(200, {"ready": voice_clone.is_ready(), "status": voice_clone.status()})
        elif self.path == "/api/voice/status":
            # her voice's live state, so the app can SHOW loading/ready/unavailable
            # instead of a silent gap. ready = warm Kokoro; warming = model loading;
            # unavailable = no neural voice (system voice used).
            try:
                from . import kokoro_tts
                self._json(200, kokoro_tts.voice_state())
            except Exception:
                self._json(200, {"state": "unavailable", "voice": "system",
                                 "detail": "voice status unavailable"})
        elif self.path.split("?")[0] == "/api/engineflow":
            # The real limbic-net activations for a phrase — so the Mind page can
            # draw the neural net as a living field (input cues → hidden neurons →
            # felt output). Honest: every number is the engine's own forward pass.
            import urllib.parse as _up
            q = _up.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "").get("q", [""])[0]
            try:
                from .. import brain as _brain
                self._json(200, _brain.engine_flow(q))
            except Exception as e:
                self._json(200, {"active": {}, "error": str(e)})
        elif self.path == "/api/activity/status":
            from .. import activity
            self._json(200, {
                "enabled": activity.is_enabled(),
                "private": activity.is_private(),
                "observing": activity.observing(),
                "status": activity.status(),
            })
        elif self.path == "/api/music/status":
            from .. import music
            self._json(200, {
                "enabled": music.is_enabled(),
                "paused": music.is_paused(),
                "status": music.status(),
            })
        elif self.path == "/api/portrait/status":
            # "See a loved one in 3D": is a face built, and is the pipeline ready?
            # Includes a "building" flag so the app can show progress while the
            # local depth + Blender build runs. Nothing here reads or sends pixels.
            from .. import portrait
            st = portrait.status()
            st["building"] = _portrait_building
            self._json(200, st)
        elif self.path == "/api/email/triage" or self.path.startswith("/api/email/triage?"):
            # "Which of my emails are junk?" — read-only IMAP triage, on-device.
            # Nothing is deleted/moved/marked; the mailbox opens read-only. IMAP
            # talks straight to the provider (Yahoo/Gmail/…), the LLM tie-breaker
            # is local. Config from env + Keychain, exactly like the CLI.
            from urllib.parse import urlparse, parse_qs
            import os as _os
            from .. import email_triage
            from ..secrets_store import get as _secret
            q = parse_qs(urlparse(self.path).query)
            try:
                limit = max(1, min(300, int(q.get("limit", ["100"])[0])))
            except ValueError:
                limit = 100
            host = _os.environ.get("IMAP_HOST")
            user = _os.environ.get("IMAP_USER")
            password = _secret("IMAP_PASSWORD")
            folder = _os.environ.get("IMAP_FOLDER", "INBOX")
            if not (host and user and password):
                # Not configured — tell the app what's missing so it can prompt.
                self._json(200, {
                    "configured": False,
                    "need": [k for k, v in (("IMAP_HOST", host), ("IMAP_USER", user),
                                            ("IMAP_PASSWORD", password)) if not v],
                    "hint": "Set IMAP_HOST + IMAP_USER, and store an app-specific "
                            "password as IMAP_PASSWORD. Yahoo: imap.mail.yahoo.com.",
                })
            else:
                try:
                    port = int(_os.environ.get("IMAP_PORT", "993"))
                    verdicts = email_triage.triage(
                        host=host, user=user, password=password, port=port,
                        folder=folder, limit=limit,
                    )
                    counts = {"good": 0, "marketing": 0, "spam": 0, "unsure": 0}
                    items = []
                    for v in verdicts:
                        counts[v.label] = counts.get(v.label, 0) + 1
                        items.append({
                            "sender": v.sender, "subject": v.subject,
                            "label": v.label, "reason": v.reason, "by": v.by,
                        })
                    self._json(200, {
                        "configured": True, "readOnly": True,
                        "total": len(verdicts), "counts": counts, "items": items,
                    })
                except Exception as e:
                    self._json(200, {"configured": True, "error": str(e)})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/api/transcribe":
            # LOCAL speech-to-text (bypasses Apple's SFSpeechRecognizer, which is
            # flaky on free-team / side-loaded builds). The app captures mic audio
            # itself (AVAudioEngine — the mic grant works) and POSTs a WAV here; we
            # transcribe it with the on-device Whisper (faster-whisper) and return
            # the text. Fully on-device, nothing leaves the machine.
            import tempfile as _tf, os as _os
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length > 0 else b""
            text = ""
            if raw[:4] == b"RIFF" and stt.is_available():
                f = _tf.NamedTemporaryFile(suffix=".wav", delete=False, dir="/tmp")
                try:
                    f.write(raw)
                    f.flush()
                    f.close()
                    try:
                        text = stt.transcribe(f.name) or ""
                    except Exception as e:  # never 500 the mic — return empty
                        import sys as _sys
                        print(f"[transcribe] {e}", file=_sys.stderr)
                        text = ""
                finally:
                    try:
                        _os.unlink(f.name)
                    except OSError:
                        pass
            text = text.strip()
            # Whisper hallucinates stock phrases on silence/noise ("Thank you.",
            # "you", "Bye.") — treat those (and anything too short) as NOT HEARD, so
            # she asks you to repeat rather than acting on a phantom. `heard` tells
            # the app it's a real utterance vs. a mishearing it should ignore.
            _low = text.lower().strip(" .!,")
            _noise = {"", "you", "thank you", "thanks", "bye", "bye.", "okay", "ok",
                      "uh", "um", "hmm", "mm", "yeah", ".", "the", "so"}
            heard = bool(text) and _low not in _noise and len(_low) >= 2
            self._json(200, {"text": text if heard else "", "heard": heard})
            return
        if self.path == "/api/health/import":
            # Import an Apple Health export (parsed locally). Body: {"path": "..."}.
            from .. import health as _health
            data = self._read_json()
            res = _health.import_export((data or {}).get("path") or "")
            self._json(200, res)
            return
        if self.path == "/api/health/activity":
            # Toggle the health sense on/off. Body: {"on": true/false}.
            from .. import health as _health
            data = self._read_json()
            _health.enable(bool((data or {}).get("on", True)))
            self._json(200, {"enabled": _health.is_enabled()})
            return
        if self.path == "/api/persona":
            # Rename / switch who she is. Body: {"name": "Emma", "about": "..."}.
            # Changing the name changes who the LLM speaks as (it's folded into the
            # system prompt). Preserves other persona fields the user set.
            from .. import persona as _persona
            data = self._read_json() or {}
            p = _persona.load()
            new_name = (data.get("name") or "").strip()
            if new_name:
                p.name = new_name
            if isinstance(data.get("about"), str):
                p.about = data["about"].strip()
            _persona.save(p)
            self._json(200, {"ok": True, "name": p.name, "about": p.about})
            return
        if self.path == "/api/personality":
            # Set personality dials. Body: {"warmth":0.7,"humor":0.4,...}.
            from .. import personality
            data = self._read_json()
            dials = personality.save(data or {})
            self._json(200, {"dials": dials})
            return
        if self.path == "/api/voice/set":
            # Switch her NEURAL (Kokoro) voice. Body: {"voice": id} (e.g. af_bella).
            # This is the picker the user actually wants. Takes effect immediately.
            from . import kokoro_tts
            data = self._read_json()
            vid = (data.get("voice") or "").strip()
            ok = kokoro_tts.set_voice(vid) if vid else False
            self._json(200, {"ok": ok, "current": kokoro_tts.current_voice()})
            return
        if self.path == "/api/voice/system":
            # Set the macOS `say` voice Vera speaks with (persisted via env for
            # this process). Body: {"voice": name}. (tts is module-level, line 29.)
            data = self._read_json()
            name = (data.get("voice") or "").strip()
            if name:
                os.environ["CTWIN_VOICE"] = name
                tts._chosen_voice = name  # take effect immediately
            self._json(200, {"current": tts.best_voice() or ""})
            return
        if self.path == "/api/voice/piper":
            # Synthesize text to a WAV with Vera's bundled NEURAL voice and return
            # the audio bytes. The brain (background service) can't PLAY audio, but
            # it can synthesize — the app plays the WAV it gets back. Prefer Kokoro
            # (expressive, human, emotional); fall back to Piper, then nothing.
            # (Endpoint name kept for app compatibility.)
            from . import kokoro_tts, piper_tts
            data = self._read_json()
            text = (data.get("text") or "").strip()
            try:
                ls = float(data.get("length_scale", 1.08))
            except (TypeError, ValueError):
                ls = 1.08
            wav = None
            if text and kokoro_tts.is_available():
                # Kokoro speed: invert length_scale (ls>1 = slower → speed<1)
                wav = kokoro_tts.synth_wav(text, speed=min(1.3, max(0.6, 1.0 / ls)))
            if wav is None and text:
                wav = piper_tts.synth_wav(text, length_scale=ls)
            if wav:
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(wav)))
                self.end_headers()
                try:
                    self.wfile.write(wav)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            else:
                # not available / failed → 204 so the app falls back to the system voice
                self.send_response(204)
                self.end_headers()
            return
        if self.path == "/api/voice/preview":
            # Speak a short sample in a given (or current) voice so the user can
            # hear it before committing — fixes "the voice is too robotic" by
            # letting them audition the better ones. (tts is module-level.)
            data = self._read_json()
            name = (data.get("voice") or "").strip() or None
            sample = (data.get("text") or "Hi — this is how I sound.").strip()
            tts.speak(sample, voice=name, blocking=False)
            self._json(200, {"ok": True})
            return
        if self.path == "/api/lockdown":
            # Trip or release the GLOBAL KILL SWITCH. Body: {"on": true/false}.
            # On → Vera halts all outward/mutating capability (net, control, email)
            # and stays dormant until explicitly released. Never auto-releases.
            from .. import security
            data = self._read_json()
            if bool(data.get("on")):
                security.lockdown(reason=(data.get("reason") or "UI kill switch"))
            else:
                security.release_lockdown()
            self._json(200, {"locked": security.is_locked()})
            return
        if self.path == "/api/thought":
            # "How she thinks": one legible pass — the retrieved docs (RAG across
            # all indexes), the felt state (mood/stress), the faculty path, and the
            # route — so the app can SHOW the pipeline simply, not a noisy galaxy.
            data = self._read_json()
            query = (data.get("text") or "").strip()
            try:
                from .. import viz
                self._json(200, viz._thought(query))
            except Exception as e:
                self._json(200, {"q": query, "error": str(e)})
            return
        if self.path == "/api/rag":
            # Visible RAG: return the top passages Vera would ground an answer on,
            # pooled across EVERY index (not just "default"), each tagged with its
            # source index. The chat UI shows these as a "Sources" strip so you can
            # SEE what grounded the reply. Read-only, on-device.
            data = self._read_json()
            query = (data.get("text") or "").strip()
            try:
                from .. import rag
                pooled = []
                for name in rag.list_indexes():
                    try:
                        for h in rag.retrieve_reranked(query, name=name, k=4):
                            if getattr(h, "text", "").strip():
                                pooled.append({
                                    "index": name,
                                    "score": round(float(getattr(h, "score", 0.0)), 3),
                                    "text": h.text.strip()[:400],
                                    "source": getattr(h, "source", "") or name,
                                })
                    except Exception:
                        continue
                pooled.sort(key=lambda d: d["score"], reverse=True)
                self._json(200, {
                    "hits": pooled[:5],
                    "mode": "semantic+keyword" if rag.embeddings_available() else "keyword-only",
                })
            except Exception as e:
                self._json(200, {"hits": [], "mode": "unavailable", "error": str(e)})
            return
        if self.path == "/api/controls/set":
            # Flip one automation/data-source toggle. Body: {"key":..., "on":bool}
            from .. import controls
            data = self._read_json()
            key = (data.get("key") or "").strip()
            on = bool(data.get("on"))
            result = controls.set_control(key, on)
            self._json(200 if "error" not in result else 400, result)
            return
        if self.path == "/api/email/triage-messages":
            # Triage messages captured by the Vera BROWSER EXTENSION from your
            # already-logged-in mail tab (Yahoo/Gmail). No password reaches Vera —
            # it classifies the visible fields the page already shows. Body:
            #   { "messages": [ {sender, subject, snippet?, hasUnsubscribeLink?} ] }
            from .. import email_triage
            data = self._read_json()
            msgs = data.get("messages")
            if not isinstance(msgs, list):
                self._json(400, {"error": "messages[] required"})
                return
            counts = {"good": 0, "marketing": 0, "spam": 0, "unsure": 0}
            items = []
            for m in msgs[:500]:
                if not isinstance(m, dict):
                    continue
                v = email_triage.classify_web(
                    sender=str(m.get("sender", "")),
                    subject=str(m.get("subject", "")),
                    snippet=str(m.get("snippet", "")),
                    has_unsub_link=bool(m.get("hasUnsubscribeLink")),
                )
                counts[v.label] = counts.get(v.label, 0) + 1
                items.append({"sender": v.sender, "subject": v.subject,
                              "label": v.label, "reason": v.reason, "by": v.by})
            self._json(200, {"source": "browser", "readOnly": True,
                             "total": len(items), "counts": counts, "items": items})
            return
        if self.path == "/api/ask":
            data = self._read_json()
            text = (data.get("text") or "").strip()
            if not text:
                self._json(400, {"error": "no text"})
                return
            agent = self.server.agent  # type: ignore[attr-defined]
            # "internal": scripted prompts (the app's greeting etc.) — answer
            # them, but never learn from them as if the user said it
            internal = bool(data.get("internal"))
            try:
                answer, route = _run_once_capture(agent, text, record=not internal)
            except Exception as e:  # never 500 the UI on an agent hiccup
                self._json(200, {"answer": _llm_error_message(e), "route": None})
                return
            self._json(200, {"answer": answer, "route": route})
        elif self.path == "/api/ask/stream":
            # the same ask, streamed: newline-delimited JSON — {"delta": "…"}
            # as the words arrive, then {"done": true, "answer", "route"}.
            # facts stay identical to /api/ask; only the arrival changes.
            data = self._read_json()
            text = (data.get("text") or "").strip()
            if not text:
                self._json(400, {"error": "no text"})
                return
            agent = self.server.agent  # type: ignore[attr-defined]
            internal = bool(data.get("internal"))
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            def _send(obj) -> None:
                try:
                    self.wfile.write((json.dumps(obj) + "\n").encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    raise
            try:
                answer, route = _run_once_capture(
                    agent, text, record=not internal,
                    on_delta=lambda d: _send({"delta": d}))
                _send({"done": True, "answer": answer, "route": route})
            except (BrokenPipeError, ConnectionResetError):
                pass                        # client went away mid-stream
            except Exception as e:
                try:
                    _send({"done": True, "answer": _llm_error_message(e), "route": None})
                except Exception:
                    pass
        elif self.path == "/api/model":
            data = self._read_json()
            name = (data.get("model") or "").strip()
            if not name:
                self._json(400, {"error": "no model"})
                return
            agent = self.server.agent  # type: ignore[attr-defined]
            backend = getattr(agent, "backend", None)
            # Pin the chosen model and turn routing off so the user's choice sticks.
            # With a multi-backend, the model id may select a different provider
            # (e.g. "lmstudio/..."), so swap the whole client, not just its name.
            if backend is not None:
                temp = getattr(agent.client, "temperature", 0.4)
                agent.client = backend.client_for(name, temperature=temp)
            elif hasattr(agent.client, "model"):
                agent.client.model = name
            agent.configured_model = name
            agent.router = None
            self._json(200, {"ok": True, "model": name})
        elif self.path == "/api/speak":
            data = self._read_json()
            text = (data.get("text") or "").strip()
            ok = False
            cloned = False
            if text:
                import os as _os
                kokoro_only = _os.environ.get("CTWIN_VOICE_KOKORO_ONLY", "").strip() \
                    in {"1", "true", "yes", "on"}
                # 1) A loved one's CLONED voice (XTTS), ONLY if genuinely set up AND
                #    not disabled. The XTTS clone is slow (6–15s renders, cold-probe
                #    hangs) and switches timbre against Kokoro — the "voice sucks /
                #    two voices" report. KOKORO_ONLY skips it entirely for ONE fast,
                #    consistent voice everywhere.
                if not kokoro_only:
                    try:
                        from .. import voice_clone
                        if voice_clone.is_ready():
                            ok = voice_clone.speak(text)
                            cloned = ok
                    except Exception:
                        ok = False
                # 2) No clone → speak in her ONE consistent built-in voice: KOKORO
                #    (the same neural voice the app plays via /api/voice/piper), never
                #    macOS `say`. Synthesize + play the WAV server-side. This keeps a
                #    single voice everywhere and can't hang on a missing clone.
                #
                #    IMPORTANT: when Kokoro IS available, we must NOT fall back to the
                #    robotic macOS `say` just because her first (cold) synth came back
                #    empty — that's the "voice reverts to the AI voice" bug. A cold
                #    load is slow, not broken: retry once (the worker is warm by then)
                #    so she keeps HER voice. `say` is only for when Kokoro truly can't run.
                kokoro_up = False
                spoke_with = "none"
                if cloned:
                    spoke_with = "clone"
                if not ok:
                    try:
                        from . import kokoro_tts
                        kokoro_up = kokoro_tts.is_available()
                        if kokoro_up:
                            kokoro_tts.warm()            # ensure warm so the 1st line is HER voice
                            wav = kokoro_tts.synth_wav(text)
                            if not wav:
                                wav = kokoro_tts.synth_wav(text)   # retry after the cold load
                            if wav:
                                _play_wav_bytes(wav)
                                ok = True
                                spoke_with = "kokoro"
                    except Exception:
                        ok = False
                # 3) macOS `say` ONLY when Kokoro genuinely isn't available (not
                #    installed) — never as a silent substitute for her real voice.
                if not ok and not kokoro_up:
                    ok = tts.speak(text, blocking=False)
                    if ok:
                        spoke_with = "system"
            # tell the caller WHICH voice spoke (so the app can be honest about it —
            # and know if it ever had to use the system voice).
            self._json(200, {"ok": ok, "cloned": cloned, "voice": spoke_with})
        elif self.path == "/api/speak/stop":
            # barge-in: the user spoke over her — silence playback mid-word
            stopped = False
            try:
                from .. import voice_clone
                stopped = voice_clone.stop_playback() or stopped
            except Exception:
                pass
            try:
                stopped = tts.stop() or stopped
            except Exception:
                pass
            self._json(200, {"ok": True, "stopped": stopped})
        elif self.path == "/api/memory/clear":
            from .. import memory
            self._json(200, {"ok": memory.clear()})
        elif self.path == "/api/voice/add":
            # Teach Anita a loved one's voice from their writing samples.
            from .. import voice_profile as vp
            data = self._read_json()
            text = data.get("text") or ""
            person = (data.get("person") or "").strip()
            n = vp.add_samples(text, person=person)
            self._json(200, {"ok": True, "samples": n, "status": vp.status()})
        elif self.path == "/api/voice/clear":
            from .. import voice_profile as vp
            self._json(200, {"ok": vp.clear_voice()})
        elif self.path == "/api/voice/clone":
            # set the loved one's voice sample for cloning (by file path)
            from .. import voice_clone
            data = self._read_json()
            path = (data.get("path") or "").strip()
            person = (data.get("person") or "").strip()
            res = voice_clone.set_reference(path, person=person) if path else {"ok": False}
            res["status"] = voice_clone.status()
            self._json(200, res)
        elif self.path == "/api/remember":
            from .. import voice_profile as vp
            data = self._read_json()
            fact = (data.get("fact") or "").strip()
            n = vp.remember(fact) if fact else len(vp.custom_facts())
            self._json(200, {"ok": bool(fact), "count": n})
        elif self.path == "/api/activity":
            # control device-activity learning + privacy. action: enable|disable|
            # private|resume|snooze|sample|clear
            from .. import activity
            data = self._read_json()
            action = (data.get("action") or "").strip()
            if action == "enable":
                activity.enable(True)
            elif action == "disable":
                activity.enable(False)
            elif action == "private":
                activity.pause(True)
            elif action == "resume":
                activity.pause(False)
            elif action == "snooze":
                activity.snooze(int(data.get("minutes", 30)))
            elif action == "sample":
                activity.sample()
            elif action == "clear":
                activity.clear()
            self._json(200, {"ok": True, "status": activity.status(),
                             "observing": activity.observing(),
                             "private": activity.is_private(),
                             "enabled": activity.is_enabled()})
        elif self.path == "/api/music":
            # control music (Now Playing) tracking. action: enable|disable|
            # sample|clear. Pause/resume ride the shared activity private mode.
            from .. import music
            data = self._read_json()
            action = (data.get("action") or "").strip()
            if action == "enable":
                music.enable()
            elif action == "disable":
                music.disable()
            elif action == "sample":
                music.sample()          # gated inside; no-op if off/paused
            elif action == "clear":
                music.clear()
            self._json(200, {"ok": True, "status": music.status(),
                             "paused": music.is_paused(),
                             "enabled": music.is_enabled()})
        elif self.path == "/api/council":
            # Ask every twin the same question and return each one's take. The
            # council builds a fresh agent per twin (pointing storage at that
            # twin's folder), then restores the env — so the shared server agent
            # and the active twin are left untouched. See cognitive_twin/council.py.
            from .. import council, twins
            data = self._read_json()
            question = (data.get("text") or data.get("question") or "").strip()
            if not question:
                self._json(400, {"error": "no question"})
                return
            # Optional subset: {"twins": ["anita", "dad"]}. Default: all twins.
            wanted = data.get("twins")
            slugs = None
            if isinstance(wanted, list) and wanted:
                slugs = [twins.slug(str(s)) for s in wanted]
            try:
                result = council.convene(question, twin_slugs=slugs)
            except Exception as e:  # never 500 the UI
                self._json(200, {"question": question, "takes": [],
                                 "error": str(e)})
                return
            takes = [
                {"slug": t.slug, "name": t.name, "answer": t.answer,
                 "model": t.model, "error": t.error}
                for t in result.takes
            ]
            self._json(200, {"question": result.question, "takes": takes})
        elif self.path == "/api/presence":
            # derived MOTION facts from the opt-in camera page (no frames,
            # no images — see presence.py). Ephemeral: latest reading only.
            from .. import presence
            presence.update(self._read_json())
            self._json(200, {"ok": True})
        elif self.path == "/api/presence/stop":
            from .. import presence
            presence.stop()
            self._json(200, {"ok": True})
        elif self.path == "/api/presence/ambient":
            # ambient sound TYPES from the opt-in ear (no audio, no recordings
            # — see presence.py). Ephemeral: latest reading only.
            from .. import presence
            presence.update_ambient(self._read_json())
            self._json(200, {"ok": True})
        elif self.path == "/api/presence/ambient/stop":
            from .. import presence
            presence.stop_ambient()
            self._json(200, {"ok": True})
        elif self.path == "/api/vault/export":
            # Settings' "Export for another device": one passphrase-encrypted
            # bundle of the memory folder, written where the user chose.
            from pathlib import Path as _P
            from .. import vault
            data = self._read_json()
            try:
                r = vault.export_bundle(_P(str(data.get("path") or "")),
                                        str(data.get("passphrase") or ""))
                self._json(200, {"ok": True, **r})
            except Exception as e:
                self._json(200, {"ok": False, "error": str(e)})
        elif self.path == "/api/photos/events":
            # life events derived from Photos METADATA (album titles + dates,
            # never pixels) — sent only while the opt-in "Read my Photos"
            # switch is on. Stored as ordinary memories, dedup-safe.
            # Also accepts "places": where you've been, from photo location
            # metadata (opt-in, on-device; reverse-geocoded in the app).
            from .. import photos
            data = self._read_json()
            result = {}
            if data.get("events"):
                result = photos.learn(data.get("events") or [])
            if data.get("places"):
                result = {**result, **photos.learn_places(data.get("places") or [])}
            if data.get("moments"):
                result = {**result, **photos.learn_moments(data.get("moments") or [])}
            self._json(200, {"ok": True, **result})
        elif self.path == "/api/portrait/build":
            # Build the 3D likeness from ONE chosen photo (opt-in "See a loved one
            # in 3D"). Unlike Photos (metadata only), this reads the photo's pixels
            # — locally: depth model + Blender, output kept on this Mac. The build
            # can take a while, so it runs on a worker thread and the app polls
            # /api/portrait/status; here we just start it.
            global _portrait_building
            data = self._read_json()
            path = (data.get("path") or "").strip()
            if not path:
                self._json(400, {"ok": False, "error": "no photo path"})
                return
            if _portrait_building:
                self._json(200, {"ok": True, "building": True})
                return
            _portrait_building = True

            def _work(p: str) -> None:
                global _portrait_building
                try:
                    from .. import portrait
                    portrait.build(p)
                finally:
                    _portrait_building = False

            threading.Thread(target=_work, args=(path,), daemon=True).start()
            self._json(200, {"ok": True, "building": True})
        elif self.path == "/api/portrait/clear":
            # Forget the face — turns the orb back to normal at once.
            from .. import portrait
            self._json(200, portrait.clear())
        elif self.path == "/api/reflect":
            # Anita thinks about your projects (while you're away) and saves a
            # thought. Best-effort; needs project seeds in memory + a reachable model.
            from .. import soul
            agent = self.server.agent  # type: ignore[attr-defined]
            instruction = soul.reflection_prompt()
            if not instruction:
                self._json(200, {"ok": False, "reason": "no projects yet"})
                return
            try:
                # record=False: the reflection instruction is scripted, not the
                # user speaking — it must never become a "memory" of them
                answer, _ = _run_once_capture(agent, instruction, record=False)
                soul.add_reflection(answer)
                self._json(200, {"ok": True, "thought": answer})
            except Exception as e:
                self._json(200, {"ok": False, "reason": str(e)})
        else:
            self._json(404, {"error": "not found"})

    # ---- static -------------------------------------------------------------
    def _serve_file(self, name: str, ctype: str) -> None:
        path = WEB_DIR / name
        try:
            self._send(200, path.read_bytes(), ctype)
        except OSError:
            self._json(404, {"error": f"missing {name}"})


def make_server(port: int = DEFAULT_PORT, model: str | None = None) -> ThreadingHTTPServer:
    """Build the HTTP server with a shared, routing-enabled agent attached."""
    httpd = ThreadingHTTPServer((HOST, port), _Handler)
    # interactive_confirm=False: the GUI has no terminal y/N; we use _voice_confirm.
    httpd.agent = build_agent(model, route=True, interactive_confirm=False)  # type: ignore[attr-defined]
    control.set_confirm(_voice_confirm)  # ensure our confirm wins after build
    _warm_voice_clone()  # preload engine detection + the XTTS model in the background
    _warm_kokoro()       # preload the neural voice so the FIRST reply isn't a 15s wait
    _warm_stt()          # preload Whisper so the FIRST spoken turn isn't a 20–30s load
    _warm_recall()       # preload activity/life-memory caches so the FIRST reply is fast
    _warm_model(httpd.agent)  # load the chat model(s) so the FIRST message isn't empty/slow
    _start_activity_sampler()  # observe device activity (only when enabled + not private)
    _start_companion_loop()    # she reaches out warmly on her own (only when enabled)
    return httpd


def _warm_model(agent) -> None:
    """Preload the chat model(s) into Ollama at startup so the user's FIRST message
    isn't met with a cold load (which came back empty / took ~30s the first time).
    Warms the configured companion model AND the routed fast-path model, since a
    real conversation uses both. Tiny prompts, discarded; fully background + fail-soft."""
    def warm() -> None:
        import time
        # which models a conversation will actually hit: the configured default
        # (companion, e.g. vera-merged) + the policy's everyday fast-path model.
        models: list[str] = []
        cfg = getattr(agent, "configured_model", None)
        if cfg:
            models.append(cfg)
        try:
            from ..agent.router import Router
            r = getattr(agent, "router", None) or Router()
            for probe in ("hi", "what's 2+2"):           # a companion + a fast turn
                m = r.route(probe).model
                if m and m not in models:
                    models.append(m)
        except Exception:
            pass
        client = getattr(agent, "client", None)
        for m in models:
            try:
                if client is not None and hasattr(client, "model"):
                    saved = client.model
                    client.model = m
                    from ..llm.ollama_client import ChatMessage
                    client.chat([ChatMessage(role="user", content="hi")])  # loads it
                    client.model = saved
            except Exception:
                pass
            time.sleep(0.2)
    threading.Thread(target=warm, daemon=True).start()


def _warm_recall() -> None:
    """Warm the recall caches off the main thread. The activity summary decrypts a
    multi-MB sealed log and life-memory loads a sealed index — each ~several seconds
    the first time. Doing it at startup (not on the first user turn) means the very
    first reply is as snappy as the rest. Both are cached by file signature, so this
    is a one-time cost that every later turn reuses. Fail-soft."""
    def warm() -> None:
        try:
            from .. import activity
            activity.summary_for_prompt()  # builds the patterns cache
        except Exception:
            pass
        try:
            from .. import life_memory
            life_memory.context_for_prompt("hello")  # builds the index cache
        except Exception:
            pass
    threading.Thread(target=warm, daemon=True).start()


def _warm_stt() -> None:
    """Preload Whisper in the background so the FIRST spoken turn transcribes in
    ~1s instead of a 20–30s cold model load. Fail-soft; purely background."""
    def warm() -> None:
        try:
            if stt.is_available():
                stt.warm()
        except Exception:
            pass
    threading.Thread(target=warm, daemon=True).start()


def _warm_kokoro() -> None:
    """Keep Vera's neural voice HOT so she speaks promptly.

    Kokoro's first synth after idle is slow (~15-25s cold) and it drifts cold again
    between replies — which made her chosen voice feel broken. So we don't just warm
    once: we warm at startup AND re-synth a tiny phrase on a heartbeat, so the model
    stays resident and warm synths stay ~0.3-1s. Fail-soft; purely background."""
    def warm_loop() -> None:
        import time
        from . import kokoro_tts
        # initial warm, RIGHT NOW (loads the model + worker so the FIRST user turn
        # is already warm — no cold synth racing startup, which was dropping the
        # connection and reverting her to the robotic voice).
        try:
            if kokoro_tts.is_available():
                kokoro_tts.warm()                 # boot the worker + model
                kokoro_tts.synth_wav("ready")     # force the slow first synth here
        except Exception:
            pass
        # heartbeat: re-synth a tiny phrase so the model never drifts cold. 45s keeps
        # a safe margin under the idle-unload window, so every real synth is on the
        # fast (~0.3-1s) warm path and never falls back.
        while True:
            time.sleep(45)
            try:
                if kokoro_tts.is_available():
                    kokoro_tts.synth_wav(".")   # tiny, cheap — just keeps it hot
            except Exception:
                pass
    threading.Thread(target=warm_loop, daemon=True).start()


def _start_activity_sampler() -> None:
    """Sample the frontmost app every ~90s so the twin learns how you work — but
    ONLY when activity learning is enabled and not in private/snooze mode. The
    privacy gate is checked inside activity.sample(), so this loop is always safe."""
    def loop():
        import time
        from .. import activity, music
        while True:
            try:
                activity.sample()   # no-op unless observing() is true
            except Exception:
                pass
            try:
                music.sample()      # no-op unless music tracking is enabled
            except Exception:
                pass
            time.sleep(90)
    threading.Thread(target=loop, daemon=True).start()


def _start_companion_loop() -> None:
    """Vera reaches out on her own — warm, chatty check-ins in her voice, so she's
    a presence, not something that only answers (Ankur: 'not just waiting for me to
    talk'). No-op unless the companion is enabled; the cadence, quiet hours, mood
    gating (no jokes in heavy moments) and speaking all live in proactive.py. She
    speaks through THIS server's /api/speak, so it's her one Kokoro voice."""
    def loop():
        import time
        from .. import proactive
        # a gentle delay so she doesn't greet the instant the service boots
        time.sleep(120)
        while True:
            try:
                # if a previous check-in went unanswered, learn a gentle "not now"
                # for that context BEFORE maybe reaching out again.
                proactive.note_ignored()
            except Exception:
                pass
            try:
                proactive.companion_checkin(speak=True)  # no-op unless due + enabled
            except Exception:
                pass
            # check every ~3 min; proactive.py decides if a line is actually due
            time.sleep(180)
    threading.Thread(target=loop, daemon=True).start()


def _warm_voice_clone() -> None:
    """Warm the cloned-voice path off the main thread: cache engine detection so
    /api/voice/clone/status is instant, and preload the XTTS model so her first
    spoken reply is fast (not a ~40s cold load)."""
    def warm():
        try:
            from .. import voice_clone
            if voice_clone.detect_engine() and voice_clone.has_reference():
                voice_clone._ensure_worker()  # loads the model, stays warm
        except Exception:
            pass
    threading.Thread(target=warm, daemon=True).start()


def _active_tts_label() -> str:
    """The TTS engine she ACTUALLY speaks with — same preference order as the
    /api/speak path (Kokoro → Piper → macOS say). The old banner always printed
    'macOS say' even when Kokoro was live, which was misleading in the logs."""
    try:
        from . import kokoro_tts
        if kokoro_tts.is_available():
            return f"Kokoro neural ({kokoro_tts.current_voice()})"
    except Exception:
        pass
    try:
        from . import piper_tts
        if piper_tts.is_available():
            return "Piper neural"
    except Exception:
        pass
    return "macOS say" if tts.is_available() else "unavailable"


def serve(port: int = DEFAULT_PORT, *, open_browser: bool = True, model: str | None = None) -> None:
    # Speak as the ACTIVE twin: point every storage module (persona, memory,
    # soul, voice, activity) at its folder, exactly like the CLI does. Without
    # this, a directly-launched server (the macOS app's path) reads the legacy
    # flat layout and becomes whoever is left in those files. An explicit
    # CTWIN_MEMORY_DIR still wins (tests / power users pin their own layout).
    import os as _os
    if "CTWIN_MEMORY_DIR" not in _os.environ:
        try:
            from .. import twins
            twins.activate()
        except Exception:
            pass
    httpd = make_server(port, model)
    url = f"http://{HOST}:{port}"
    print(f"Vera · Siri UI at {url}")
    print(f"  voice: {_active_tts_label()} · {stt.status()}")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye.")
        httpd.shutdown()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(prog="twin-voice", description="Local Siri-style voice UI for the Cognitive Twin.")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-open", action="store_true", help="don't auto-open the browser")
    ap.add_argument("--model", help="pin a model (otherwise policy routing chooses)")
    args = ap.parse_args()
    serve(args.port, open_browser=not args.no_open, model=args.model)
