from __future__ import annotations

import os
import subprocess
from pathlib import Path

import rumps


class TwinMenuBar(rumps.App):
    def __init__(self) -> None:
        super().__init__("Twin")
        self.workspace_root = Path(os.getenv("AGENT_WORKSPACE_ROOT", ".")).resolve()
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
        pid_file = self.workspace_root / "memory" / "runtime" / "daemon.pid"
        if pid_file.exists():
            rumps.notification("Cognitive Twin", "Status", "Daemon appears active")
        else:
            rumps.notification("Cognitive Twin", "Status", "Daemon is not running")

    @rumps.clicked("Start Daemon")
    def start_daemon(self, _):
        token = os.getenv("AGENT_DAEMON_TOKEN", "")
        if not token:
            rumps.alert("Set AGENT_DAEMON_TOKEN before starting daemon")
            return

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
        pid_file = self.workspace_root / "memory" / "runtime" / "daemon.pid"
        if not pid_file.exists():
            rumps.alert("No daemon PID file found")
            return

        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
            os.kill(pid, 15)
            pid_file.unlink(missing_ok=True)
            rumps.notification("Cognitive Twin", "Daemon", "Stop signal sent")
        except Exception as exc:
            rumps.alert(f"Failed to stop daemon: {exc}")

    @rumps.clicked("Quick Voice Trigger")
    def quick_voice_trigger(self, _):
        token = os.getenv("AGENT_DAEMON_TOKEN", "")
        if not token:
            rumps.alert("Set AGENT_DAEMON_TOKEN before quick trigger")
            return

        cmd = [
            "python3",
            "src/multimodal_orchestrator.py",
            "--task",
            "Give me one immediate next action",
            "--enable-audio",
            "--enable-transcription",
            "--consent",
            "I AGREE",
        ]
        subprocess.Popen(cmd, cwd=str(self.workspace_root))
        rumps.notification("Cognitive Twin", "Quick Trigger", "Voice-trigger run started")

    @rumps.clicked("Open Latest Output")
    def open_output(self, _):
        path = self.workspace_root / "memory" / "runtime" / "latest_assistant_output.md"
        if not path.exists():
            rumps.alert("No output file yet")
            return
        subprocess.Popen(["open", str(path)])


if __name__ == "__main__":
    TwinMenuBar().run()
