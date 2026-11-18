"""
Menubar — Vera's control surface, Tailscale-style.

Ankur's brief: a switch like Tailscale, matched to Tailscale's quality, with the
user *in control for sure*. So this menu-bar app is where you see, at a glance,
WHO can reach Vera and whether she can act — and flip any of it:

  ● status line           who can reach her + can she act (one glance = truth)
  Reach   🔒 Private / 📱 My devices     loopback vs token-gated tailnet
  Safe Mode  (on by default)             reads/chats freely, asks before acting
  🚫 Kill Switch (lockdown)              halts everything; think-only
  Developer ▸                            ports, device token, bind host (opt-in)

Identity is Vera's own (see docs/CONTROL-SURFACE-BRAND.md): warm amber on
near-black, red for danger only — not a teal security clone. (rumps renders the
native menu; the color story is carried fully in the web /settings panel, which
this links to. The menu uses symbols + plain words to signal state.)

All state lives in cognitive_twin.privacy (reach, safe mode, device token) and
cognitive_twin.security (the kill switch) — this is just the native face on it.

Optional dependency:  pip install rumps
Run:  python -m cognitive_twin.voice.menubar
"""

from __future__ import annotations

import sys
import threading
import webbrowser

from .server import make_server, DEFAULT_PORT, _active_tts_label
from . import stt
from .. import privacy, security


def _require_rumps():
    try:
        import rumps  # noqa: F401
        return rumps
    except ImportError:
        print(
            "The menubar app needs rumps:  pip install rumps\n"
            "Meanwhile the same control surface runs in your browser:\n"
            "  python -m cognitive_twin.voice.server   (then open /settings)",
            file=sys.stderr,
        )
        raise SystemExit(1)


# ── the glyph that signals the whole posture at a glance (menu-bar title) ───────
def _title_glyph() -> str:
    if security.is_locked():
        return "🚫"            # kill switch — she can't act
    if privacy.reach() == privacy.MY_DEVICES:
        return "🟡"            # reachable by your devices (amber = Vera's brand)
    return "🎙"               # private, this Mac only (default)


def run(port: int = DEFAULT_PORT) -> None:
    rumps = _require_rumps()

    # Start the local server in a background thread, bound per the privacy switch
    # (Private → loopback, My devices → tailnet). The switch is the source of truth.
    httpd = make_server(port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    # the host the UI is actually reachable at for THIS Mac is always loopback
    base = f"http://127.0.0.1:{port}"

    class VeraApp(rumps.App):
        def __init__(self) -> None:
            super().__init__(_title_glyph(), quit_button=None)
            # Built once; refreshed live by _refresh() on a timer so the menu always
            # tells the truth even if state changed elsewhere (CLI, web, phone).
            self.status_item = rumps.MenuItem("", callback=None)
            self.reach_private = rumps.MenuItem("🔒 Private (this Mac only)",
                                                callback=self.set_private)
            self.reach_devices = rumps.MenuItem("📱 My devices (tailnet)",
                                                callback=self.set_my_devices)
            self.safe_item = rumps.MenuItem("Safe Mode", callback=self.toggle_safe)
            self.kill_item = rumps.MenuItem("🚫 Kill Switch (lockdown)",
                                            callback=self.toggle_kill)
            self.menu = [
                self.status_item,
                None,
                rumps.MenuItem("Reach", callback=None),
                self.reach_private,
                self.reach_devices,
                None,
                self.safe_item,
                self.kill_item,
                None,
                rumps.MenuItem("Open Vera…", callback=self.open_panel),
                rumps.MenuItem("Settings…", callback=self.open_settings),
                ("Developer", [
                    rumps.MenuItem("Show device pairing token…", callback=self.show_token),
                    rumps.MenuItem("Rotate device token (un-pairs all)", callback=self.rotate_token),
                    None,
                    rumps.MenuItem(f"Voice: {_active_tts_label()}", callback=None),
                    rumps.MenuItem(stt.status(), callback=None),
                    rumps.MenuItem(f"Port: {port}", callback=None),
                    rumps.MenuItem("Open web Developer settings…", callback=self.open_dev),
                ]),
                None,
                rumps.MenuItem("Quit", callback=self.quit),
            ]
            self._refresh()

        # ── live state → menu labels + checkmarks (one glance = truth) ──────────
        def _refresh(self, _=None):
            e = privacy.explain()
            locked = e["locked"]
            # top status line: who can reach + can she act
            if locked:
                self.status_item.title = "🚫  Locked down — think only, can't act"
            else:
                act = "asks before acting" if e["safe_mode"] else "may act freely"
                self.status_item.title = f"●  {e['reach_label'].split(' ', 1)[1]} · {act}"
            # reach radio
            self.reach_private.state = 1 if e["reach"] == privacy.PRIVATE else 0
            self.reach_devices.state = 1 if e["reach"] == privacy.MY_DEVICES else 0
            # safe mode + kill switch checks
            self.safe_item.state = 1 if e["safe_mode"] else 0
            self.kill_item.state = 1 if locked else 0
            # the menu-bar glyph itself
            self.title = _title_glyph()

        # ── actions (every one is an explicit user choice; all are logged) ──────
        def set_private(self, _):
            privacy.set_reach(privacy.PRIVATE)
            self._note("Private", "Only this Mac can reach Vera now. "
                       "Restart Vera to re-bind to loopback.")
            self._refresh()

        def set_my_devices(self, _):
            privacy.set_reach(privacy.MY_DEVICES)
            tok = privacy.token()
            self._note("My devices", "Your devices can reach Vera over Tailscale "
                       "with the pairing token (Developer ▸ shows it). "
                       "Restart Vera to re-bind.\n\nToken: " + (tok or "—"))
            self._refresh()

        def toggle_safe(self, _):
            privacy.set_safe_mode(not privacy.safe_mode())
            self._refresh()

        def toggle_kill(self, _):
            if security.is_locked():
                security.release_lockdown()
            else:
                security.lockdown("menubar")
            self._refresh()

        def show_token(self, _):
            self._note("Device pairing token",
                       (privacy.token() or "No token yet — turn on 'My devices' first."))

        def rotate_token(self, _):
            new = privacy.rotate_token()
            self._note("Token rotated",
                       "Every device must re-pair with the new token:\n\n" + new)

        def open_panel(self, _):
            webbrowser.open(f"{base}/?listen=1")

        def open_settings(self, _):
            webbrowser.open(f"{base}/settings")

        def open_dev(self, _):
            webbrowser.open(f"{base}/settings#developer")

        def _note(self, title: str, message: str):
            try:
                rumps.alert(title=f"Vera — {title}", message=message, ok="OK")
            except Exception:
                pass

        def quit(self, _):
            httpd.shutdown()
            rumps.quit_application()

    app = VeraApp()
    # refresh the menu's truth every few seconds (state can change from CLI/web/phone)
    rumps.Timer(app._refresh, 4).start()
    app.run()


if __name__ == "__main__":
    run()
