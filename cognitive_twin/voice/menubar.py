"""
Menubar launcher — a thin macOS menubar mic for Vera.

Lives in the menu bar; clicking "Speak" opens the Siri panel and starts listening.
The actual work (STT in the browser, agent, TTS via `say`) runs through the local
server. This file is deliberately thin — the verifiable substance is the server +
web UI; this just launches them natively.

Optional dependency:  pip install rumps
Run:  python -m cognitive_twin.voice.menubar
"""

from __future__ import annotations

import sys
import threading
import webbrowser

from .server import make_server, HOST, DEFAULT_PORT
from . import tts, stt


def _require_rumps():
    try:
        import rumps  # noqa: F401
        return rumps
    except ImportError:
        print(
            "The menubar app needs rumps:  pip install rumps\n"
            "Meanwhile the same Siri UI runs in your browser:\n"
            "  python -m cognitive_twin.voice.server",
            file=sys.stderr,
        )
        raise SystemExit(1)


def run(port: int = DEFAULT_PORT) -> None:
    rumps = _require_rumps()

    # Start the local server in a background thread.
    httpd = make_server(port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://{HOST}:{port}"

    class VeraApp(rumps.App):
        def __init__(self) -> None:
            super().__init__("🎙", quit_button=None)
            self.menu = [
                rumps.MenuItem("Speak to the Twin", callback=self.speak),
                rumps.MenuItem("Open panel", callback=self.open_panel),
                None,
                rumps.MenuItem(f"TTS: {'macOS say' if tts.is_available() else 'off'}", callback=None),
                rumps.MenuItem(stt.status(), callback=None),
                None,
                rumps.MenuItem("Quit", callback=self.quit),
            ]

        def speak(self, _):
            webbrowser.open(f"{base}/?listen=1")

        def open_panel(self, _):
            webbrowser.open(base)

        def quit(self, _):
            httpd.shutdown()
            rumps.quit_application()

    VeraApp().run()


if __name__ == "__main__":
    run()
