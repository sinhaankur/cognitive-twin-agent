from __future__ import annotations

import os
import subprocess
from pathlib import Path

import rumps

from ipc_channel import SignedLocalIPC


class TwinMenuBar(rumps.App):
    def __init__(self) -> None:
        super().__init__("Twin")
        self.workspace_root = Path(os.getenv("AGENT_WORKSPACE_ROOT", ".")).resolve()
        self.ipc = SignedLocalIPC(self.workspace_root)
        self.menu = [
            "Status",
            "Start Daemon",
            "Stop Daemon",
            None,
            "Quick Voice Trigger",
            None,
            "Open Latest Output",
            "Quit",
        ]

    @rumps.clicked("Status")
    def status(self, _):
        try:
            response = self.ipc.send("status")
            if response.get("ok"):
                msg = f"active · iterations {response.get('completed_iterations', 0)}"
                rumps.notification("Cognitive Twin", "Status", msg)
                return
        except Exception:
            pass

        rumps.notification("Cognitive Twin", "Status", "Daemon is not running")

    @rumps.clicked("Start Daemon")
    def start_daemon(self, _):
        token = os.getenv("AGENT_DAEMON_TOKEN", "")
        if not token:
            rumps.alert("Set AGENT_DAEMON_TOKEN before starting daemon")
            return

        try:
            response = self.ipc.send("status")
            if response.get("ok"):
                rumps.notification("Cognitive Twin", "Daemon", "Already running")
                return
        except Exception:
            pass

        cmd = [
            "python3",
            "src/assistant_daemon.py",
            "run",
            "--token",
            token,
            "--iterations",
            "999999",
            "--interval",
            "300",
        ]

        proc = subprocess.Popen(cmd, cwd=str(self.workspace_root))
        pid_file = self.workspace_root / "memory" / "runtime" / "daemon.pid"
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(proc.pid), encoding="utf-8")
        rumps.notification("Cognitive Twin", "Daemon", f"Started PID {proc.pid}")

    @rumps.clicked("Stop Daemon")
    def stop_daemon(self, _):
        try:
            response = self.ipc.send("stop")
            if response.get("ok"):
                rumps.notification("Cognitive Twin", "Daemon", "Stop requested")
            else:
                rumps.alert(f"Daemon refused stop: {response}")
        except Exception as exc:
            rumps.alert(f"Failed to stop daemon: {exc}")

    @rumps.clicked("Quick Voice Trigger")
    def quick_voice_trigger(self, _):
        try:
            response = self.ipc.send("quick_voice_trigger")
            if response.get("ok"):
                rumps.notification("Cognitive Twin", "Quick Trigger", "Queued in daemon")
            else:
                rumps.alert(f"Quick trigger failed: {response}")
        except Exception as exc:
            rumps.alert(f"Failed to reach daemon: {exc}")

    @rumps.clicked("Open Latest Output")
    def open_output(self, _):
        path = self.workspace_root / "memory" / "runtime" / "latest_assistant_output.md"
        if not path.exists():
            rumps.alert("No output file yet")
            return
        subprocess.Popen(["open", str(path)])


if __name__ == "__main__":
    TwinMenuBar().run()
