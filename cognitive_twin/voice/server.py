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


WEB_DIR = Path(__file__).resolve().parent / "web"
HOST = "127.0.0.1"
DEFAULT_PORT = 7878


class _Handler(BaseHTTPRequestHandler):
    # the shared agent is attached to the server instance
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # local-only app; allow the page's fetch calls
        self.send_header("Access-Control-Allow-Origin", "http://%s:%d" % (HOST, self.server.server_address[1]))
        self.end_headers()
        self.wfile.write(body)

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
        elif self.path == "/eye":
            # the app's small preview window (see eye.html header note)
            self._serve_file("eye.html", "text/html; charset=utf-8")
        elif self.path == "/api/health":
            agent = self.server.agent  # type: ignore[attr-defined]
            model = getattr(agent.client, "model", None) or getattr(agent, "configured_model", None)
            self._json(200, {
                "ok": True,
                "tts": tts.is_available(),
                "stt_local": stt.is_available(),
                "model": model,
            })
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
        elif self.path == "/api/voice/clone/status":
            from .. import voice_clone
            self._json(200, {"ready": voice_clone.is_ready(), "status": voice_clone.status()})
        elif self.path == "/api/activity/status":
            from .. import activity
            self._json(200, {
                "enabled": activity.is_enabled(),
                "private": activity.is_private(),
                "observing": activity.observing(),
                "status": activity.status(),
            })
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
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
                self._json(200, {"answer": f"(error: {e})", "route": None})
                return
            self._json(200, {"answer": answer, "route": route})
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
            if text:
                # Prefer the loved one's cloned voice if it's set up; otherwise
                # fall back to the warm built-in voice so speech always works.
                try:
                    from .. import voice_clone
                    if voice_clone.is_ready():
                        ok = voice_clone.speak(text)
                except Exception:
                    ok = False
                if not ok:
                    ok = tts.speak(text, blocking=False)
            self._json(200, {"ok": ok, "cloned": ok and self._cloned_ready()})
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
            from .. import photos
            data = self._read_json()
            result = photos.learn(data.get("events") or [])
            self._json(200, {"ok": True, **result})
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
    _start_activity_sampler()  # observe device activity (only when enabled + not private)
    return httpd


def _start_activity_sampler() -> None:
    """Sample the frontmost app every ~90s so the twin learns how you work — but
    ONLY when activity learning is enabled and not in private/snooze mode. The
    privacy gate is checked inside activity.sample(), so this loop is always safe."""
    def loop():
        import time
        from .. import activity
        while True:
            try:
                activity.sample()   # no-op unless observing() is true
            except Exception:
                pass
            time.sleep(90)
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
    print(f"  TTS: {'macOS say' if tts.is_available() else 'unavailable'} · {stt.status()}")
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
