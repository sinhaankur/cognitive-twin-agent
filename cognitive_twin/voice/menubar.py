"""
Menubar — Vera's control surface, built to LITERALLY mimic Tailscale's native menu.

Ankur showed the real Tailscale menu and said: "literally mimic this · of this
standard · native as hell." So this maps Tailscale's menu 1:1 onto Vera:

  Tailscale                                   Vera (this menu)
  ─────────────────────────────────────────   ────────────────────────────────────
  Tailscale            [big toggle] Connected  Vera            [Connect toggle] state
  avatar · you@github                       ›  avatar · you · Companion + Coding
  This Device: name (100.x.y.z)                This Device: name (100.x.y.z)
  Network Devices                           ›  My Devices (paired)               ›
  Exit Nodes                                ›  Reach · Safe Mode · Kill Switch   ›
  Settings…                               ⌘,   Settings…                        ⌘,
  Open Tailscale                               Open Vera
  Quit                                    ⌘Q   Quit                             ⌘Q

The "Connect" toggle is the reach switch (Private ⇄ My devices) — exactly like
Tailscale's connect toggle. Identity is Vera's own (warm amber, see
docs/CONTROL-SURFACE-BRAND.md); the native menu carries it with symbols + plain
words. All state lives in cognitive_twin.privacy + .security; this is the face.

Optional dependency:  pip install rumps
Run:  python -m cognitive_twin.voice.menubar
"""

from __future__ import annotations

import os
import socket
import subprocess
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


# ── this device's tailnet identity (to show 'This Device: name (100.x)') ────────
def _tailscale_bin() -> str | None:
    for p in ("tailscale", "/Applications/Tailscale.app/Contents/MacOS/Tailscale"):
        if os.path.sep in p:
            if os.path.exists(p):
                return p
        else:
            from shutil import which
            w = which(p)
            if w:
                return w
    return None


def _this_device() -> tuple[str, str | None]:
    """(hostname, tailnet-ip) — mirrors Tailscale's 'This Device' line. Falls back
    to the plain hostname when Tailscale isn't present."""
    host = socket.gethostname().split(".")[0]
    ts = _tailscale_bin()
    if ts:
        try:
            ip = subprocess.run([ts, "ip", "-4"], capture_output=True, text=True,
                                timeout=3).stdout.strip().splitlines()
            if ip:
                return host, ip[0].strip()
        except Exception:
            pass
    return host, None


def _account_label() -> str:
    """The 'you@tailnet' identity row, like Tailscale shows the logged-in account.
    Uses the tailnet login name if readable, else the OS user."""
    ts = _tailscale_bin()
    if ts:
        try:
            out = subprocess.run([ts, "status", "--self", "--peers=false"],
                                 capture_output=True, text=True, timeout=3).stdout
            # columns: ip  host  login  os ...
            parts = out.split()
            if len(parts) >= 3 and "@" in parts[2]:
                return parts[2].rstrip("@") if parts[2].endswith("@") else parts[2]
        except Exception:
            pass
    return os.environ.get("USER", "you")


def _connected() -> bool:
    """Tailscale's 'Connected' = our 'reachable by my devices'. The big toggle."""
    return privacy.reach() == privacy.MY_DEVICES and not security.is_locked()


def _title_glyph() -> str:
    if security.is_locked():
        return "🚫"            # kill switch — dormant
    if privacy.reach() == privacy.MY_DEVICES:
        return "🟡"            # connected to your devices (amber = Vera)
    return "🎙"               # private, this Mac only


def run(port: int = DEFAULT_PORT) -> None:
    rumps = _require_rumps()

    httpd = make_server(port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    host, ts_ip = _this_device()

    class VeraApp(rumps.App):
        def __init__(self) -> None:
            super().__init__(_title_glyph(), quit_button=None)

            # ── top block: name + big Connect toggle + status (Tailscale's header)
            # rumps has no header widget, so the FIRST item IS the toggle — its
            # title flips "Connect" ⇄ "Connected", with a checkmark like the switch.
            self.connect_item = rumps.MenuItem("Connect", callback=self.toggle_connect)
            self.status_line = rumps.MenuItem("", callback=None)   # "Connected" / "Private"

            # ── identity row (Tailscale's avatar · you@github ›) ────────────────
            self.account_item = rumps.MenuItem(f"  {_account_label()}", callback=self.open_settings)
            self.modes_line = rumps.MenuItem("  Companion + Coding", callback=None)

            # ── this device (Tailscale's 'This Device: name (100.x)') ───────────
            dev = f"This Device: {host}" + (f" ({ts_ip})" if ts_ip else "")
            self.device_item = rumps.MenuItem(dev, callback=None)

            # ── submenus (Tailscale's Network Devices › / Exit Nodes ›) ─────────
            self.reach_private = rumps.MenuItem("🔒 Private (this Mac only)", callback=self.set_private)
            self.reach_devices = rumps.MenuItem("📱 My devices (tailnet)", callback=self.set_my_devices)
            self.safe_item = rumps.MenuItem("Safe Mode — ask before acting", callback=self.toggle_safe)
            self.kill_item = rumps.MenuItem("🚫 Kill Switch (lockdown)", callback=self.toggle_kill)

            settings_item = rumps.MenuItem("Settings…", callback=self.open_settings, key=",")

            self.menu = [
                self.connect_item,
                self.status_line,
                None,
                self.account_item,
                self.modes_line,
                None,
                self.device_item,
                ("My Devices", [
                    rumps.MenuItem("Show pairing token…", callback=self.show_token),
                    rumps.MenuItem("Rotate token (un-pairs all devices)", callback=self.rotate_token),
                    None,
                    rumps.MenuItem("Open Vera on this device", callback=self.open_panel),
                ]),
                ("Controls", [
                    rumps.MenuItem("Reach:", callback=None),
                    self.reach_private,
                    self.reach_devices,
                    None,
                    self.safe_item,
                    self.kill_item,
                ]),
                ("Developer", [
                    rumps.MenuItem(f"Voice: {_active_tts_label()}", callback=None),
                    rumps.MenuItem(stt.status(), callback=None),
                    rumps.MenuItem(f"Port: {port}", callback=None),
                    rumps.MenuItem(f"Bind: {privacy.bind_host()}", callback=None),
                    None,
                    rumps.MenuItem("Open web Developer settings…", callback=self.open_dev),
                ]),
                None,
                settings_item,
                rumps.MenuItem("Open Vera", callback=self.open_panel),
                rumps.MenuItem("Quit", callback=self.quit, key="q"),
            ]
            self._refresh()

        # ── live truth → labels, checks, glyph (one glance = state) ─────────────
        def _refresh(self, _=None):
            e = privacy.explain()
            locked = e["locked"]
            connected = _connected()
            # the big Connect toggle (Tailscale's switch)
            self.connect_item.title = "Connected" if connected else "Connect"
            self.connect_item.state = 1 if connected else 0
            # status line under it
            if locked:
                self.status_line.title = "  Locked down · think only"
            elif connected:
                self.status_line.title = "  Connected · your devices can reach Vera"
            else:
                self.status_line.title = "  Private · this Mac only"
            # radios + checks
            self.reach_private.state = 1 if e["reach"] == privacy.PRIVATE else 0
            self.reach_devices.state = 1 if e["reach"] == privacy.MY_DEVICES else 0
            self.safe_item.state = 1 if e["safe_mode"] else 0
            self.kill_item.state = 1 if locked else 0
            self.title = _title_glyph()

        # ── actions (each an explicit user choice; all logged in privacy.py) ────
        def toggle_connect(self, _):
            # the Tailscale connect toggle = flip reach between Private and My devices
            if _connected():
                privacy.set_reach(privacy.PRIVATE)
                self._note("Disconnected", "Vera is Private again — only this Mac can "
                           "reach her. Restart Vera to re-bind to loopback.")
            else:
                privacy.set_reach(privacy.MY_DEVICES)
                self._note("Connected", "Your devices can reach Vera over Tailscale "
                           "with the pairing token (My Devices ▸ shows it). Restart "
                           "Vera to re-bind.")
            self._refresh()

        def set_private(self, _):
            privacy.set_reach(privacy.PRIVATE); self._refresh()

        def set_my_devices(self, _):
            privacy.set_reach(privacy.MY_DEVICES); self._refresh()

        def toggle_safe(self, _):
            privacy.set_safe_mode(not privacy.safe_mode()); self._refresh()

        def toggle_kill(self, _):
            security.release_lockdown() if security.is_locked() else security.lockdown("menubar")
            self._refresh()

        def show_token(self, _):
            self._note("Device pairing token",
                       privacy.token() or "No token yet — Connect (My devices) first.")

        def rotate_token(self, _):
            self._note("Token rotated",
                       "Every device must re-pair with:\n\n" + privacy.rotate_token())

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
            httpd.shutdown(); rumps.quit_application()

    app = VeraApp()
    rumps.Timer(app._refresh, 4).start()  # keep the menu honest if state changes elsewhere
    app.run()


if __name__ == "__main__":
    run()
