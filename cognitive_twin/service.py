"""service — register Vera's dashboard to run (and heal) as a background service.

WatchTower-style: run it on any computer you own, keep it up automatically, reach
it privately over your tailnet. One command installs the right native service for
the platform:

  • macOS   → launchd  LaunchAgent (KeepAlive: relaunches if it dies / after login)
  • Linux   → systemd  --user unit (Restart=always; `loginctl enable-linger` to
              survive logout on the home server)
  • Windows → Scheduled Task at logon (restart-on-failure)

All private by default (binds 127.0.0.1). Pass --host 0.0.0.0 to reach it from
your other devices over Tailscale (use THIS machine's tailnet name, never a raw
100.x address on iOS).

    vera-service install                 # auto-start on this machine, localhost
    vera-service install --host 0.0.0.0  # also reachable over the tailnet
    vera-service install --port 8677
    vera-service status
    vera-service uninstall

Nothing here needs root — launchd LaunchAgent, systemd --user, and a per-user
Scheduled Task are all rootless, matching WatchTower's rootless promise.

© Ankur Sinha. Personal use.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

LABEL = "com.sinhaankur.vera-dashboard"
DEFAULT_PORT = 8677


def _python() -> str:
    """The interpreter to run the dashboard with — the current one."""
    return sys.executable or "python3"


def _run_args(port: int, host: str) -> list[str]:
    # Launch via the module so it works whether or not the console script is on
    # PATH inside the service's minimal environment.
    args = [_python(), "-m", "cognitive_twin.dashboard", "--no-open", "--port", str(port)]
    if host and host != "127.0.0.1":
        args += ["--host", host]
    return args


def _repo_root() -> Path:
    # service.py lives in cognitive_twin/; the working dir for the service is the
    # repo root (so agent_config.json etc. resolve as they do interactively).
    return Path(__file__).resolve().parent.parent


# ── macOS (launchd) ───────────────────────────────────────────────────────────
def _launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _install_macos(port: int, host: str) -> str:
    args = _run_args(port, host)
    arg_xml = "\n".join(f"    <string>{a}</string>" for a in args)
    logs = _repo_root() / "vera-dashboard.log"
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key><array>
{arg_xml}
  </array>
  <key>WorkingDirectory</key><string>{_repo_root()}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{logs}</string>
  <key>StandardErrorPath</key><string>{logs}</string>
</dict></plist>
"""
    p = _launchd_plist_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(plist, encoding="utf-8")
    subprocess.run(["launchctl", "unload", str(p)], capture_output=True)
    r = subprocess.run(["launchctl", "load", str(p)], capture_output=True, text=True)
    if r.returncode != 0:
        return f"[error] launchctl load failed: {r.stderr.strip()}"
    return f"Installed launchd service {LABEL} (auto-starts + relaunches). Plist: {p}"


def _uninstall_macos() -> str:
    p = _launchd_plist_path()
    if not p.exists():
        return "Not installed (no launchd plist)."
    subprocess.run(["launchctl", "unload", str(p)], capture_output=True)
    p.unlink(missing_ok=True)
    return f"Removed launchd service {LABEL}."


def _status_macos() -> str:
    r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    on = LABEL in r.stdout
    return f"launchd: {'running/registered' if on else 'not registered'} ({LABEL})"


# ── Linux (systemd --user) ────────────────────────────────────────────────────
def _systemd_unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / "vera-dashboard.service"


def _install_linux(port: int, host: str) -> str:
    args = _run_args(port, host)
    exec_start = " ".join(args)
    unit = f"""[Unit]
Description=Vera dashboard (settings/control panel)
After=network-online.target

[Service]
Type=simple
WorkingDirectory={_repo_root()}
ExecStart={exec_start}
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
"""
    p = _systemd_unit_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(unit, encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    r = subprocess.run(["systemctl", "--user", "enable", "--now", "vera-dashboard.service"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return f"[error] systemctl enable failed: {r.stderr.strip()}"
    hint = ("\nTip: `loginctl enable-linger $USER` so it keeps running after you log out "
            "(home-server mode).")
    return f"Installed systemd --user service (Restart=always). Unit: {p}{hint}"


def _uninstall_linux() -> str:
    p = _systemd_unit_path()
    subprocess.run(["systemctl", "--user", "disable", "--now", "vera-dashboard.service"],
                   capture_output=True)
    existed = p.exists()
    p.unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    return "Removed systemd --user service." if existed else "Not installed (no systemd unit)."


def _status_linux() -> str:
    r = subprocess.run(["systemctl", "--user", "is-active", "vera-dashboard.service"],
                       capture_output=True, text=True)
    return f"systemd --user: {r.stdout.strip() or 'unknown'}"


# ── Windows (Scheduled Task at logon) ─────────────────────────────────────────
def _install_windows(port: int, host: str) -> str:
    args = _run_args(port, host)
    # schtasks wants one command string; quote the exe + args.
    cmd = " ".join(f'"{a}"' if " " in a else a for a in args)
    r = subprocess.run(
        ["schtasks", "/Create", "/TN", "VeraDashboard", "/SC", "ONLOGON",
         "/RL", "LIMITED", "/F", "/TR", cmd],
        capture_output=True, text=True)
    if r.returncode != 0:
        return f"[error] schtasks create failed: {r.stderr.strip() or r.stdout.strip()}"
    # Start it now too (don't wait for the next logon).
    subprocess.run(["schtasks", "/Run", "/TN", "VeraDashboard"], capture_output=True)
    return "Installed Windows Scheduled Task 'VeraDashboard' (runs at logon)."


def _uninstall_windows() -> str:
    r = subprocess.run(["schtasks", "/Delete", "/TN", "VeraDashboard", "/F"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return "Not installed (no scheduled task)."
    return "Removed Windows Scheduled Task 'VeraDashboard'."


def _status_windows() -> str:
    r = subprocess.run(["schtasks", "/Query", "/TN", "VeraDashboard"],
                       capture_output=True, text=True)
    return "Scheduled Task: present" if r.returncode == 0 else "Scheduled Task: not found"


# ── dispatch ──────────────────────────────────────────────────────────────────
def _os() -> str:
    s = platform.system().lower()
    if s == "darwin":
        return "macos"
    if s == "windows":
        return "windows"
    return "linux"


_TABLE = {
    "macos":   (_install_macos, _uninstall_macos, _status_macos),
    "linux":   (_install_linux, _uninstall_linux, _status_linux),
    "windows": (_install_windows, _uninstall_windows, _status_windows),
}


def main() -> int:
    argv = sys.argv[1:]
    action = argv[0] if argv else "status"
    port = DEFAULT_PORT
    host = "127.0.0.1"
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    if "--host" in argv:
        host = argv[argv.index("--host") + 1]

    install, uninstall, status = _TABLE[_os()]
    if action == "install":
        print(install(port, host))
        shown = "127.0.0.1" if host in ("0.0.0.0", "::") else host
        print(f"→ http://{shown}:{port}/settings")
        if host in ("0.0.0.0", "::"):
            print("  (reachable over your tailnet by this machine's Tailscale name)")
    elif action == "uninstall":
        print(uninstall())
    elif action in ("status", ""):
        print(status())
    else:
        print(f"usage: vera-service [install|uninstall|status] [--port N] [--host H]")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
