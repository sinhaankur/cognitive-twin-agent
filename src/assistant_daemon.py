from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import random
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

from openai import OpenAI

from consent_manager import ConsentManager
from day_mapper import build_day_map, day_map_to_prompt
from google_oauth import GoogleOAuthManager
from ipc_channel import SignedLocalIPC
from local_orchestrator import load_text, run_agent_task, Toolbox
from local_runtime_state import RuntimeStateHandle
from oauth_loopback_server import wait_for_oauth_callback
from security_manager import SecurityManager


def init_command(workspace_root: Path, username: str) -> None:
    manager = SecurityManager(workspace_root)
    token = manager.init_user(username=username)
    print("Security initialized.")
    print(f"Allowed user: {username}")
    print("Save this token securely. It will not be shown again:")
    print(token)


def add_user_command(workspace_root: Path, username: str) -> None:
    manager = SecurityManager(workspace_root)
    manager.add_allowed_user(username)
    print(f"User added: {username}")


def status_command(workspace_root: Path) -> None:
    manager = SecurityManager(workspace_root)
    consent = ConsentManager(workspace_root)
    google = GoogleOAuthManager()
    payload = {
        "security": manager.status(),
        "connector_consents": consent.status(),
        "google_oauth": google.status(),
    }
    print(json.dumps(payload, ensure_ascii=True, indent=2))


def consent_command(workspace_root: Path, connector: str, allow: bool) -> None:
    consent = ConsentManager(workspace_root)
    consent.set_consent(connector, allow)
    state = "granted" if allow else "revoked"
    print(f"Consent {state} for connector: {connector}")


def google_oauth_begin(
    auto_capture: bool,
    open_browser: bool,
    timeout_seconds: int,
    max_attempts: int,
) -> None:
    manager = GoogleOAuthManager()
    attempts = max(1, max_attempts)

    for attempt in range(1, attempts + 1):
        result = manager.begin_auth()
        print("Open this URL and approve access:")
        print(result["authorization_url"])
        print(f"State: {result['state']}")

        if open_browser:
            webbrowser.open(result["authorization_url"], new=2)
            print("Opened browser automatically.")

        if not auto_capture:
            return

        print("Waiting for callback on http://127.0.0.1:8765/callback ...")
        callback = wait_for_oauth_callback(timeout_seconds=timeout_seconds)
        code = callback.get("code", "")
        state = callback.get("state", "")
        if code and state:
            manager.exchange_code(code=code, state=state)
            print("OAuth tokens stored securely in keychain.")
            return

        if attempt < attempts:
            print(f"OAuth callback timed out, retrying ({attempt}/{attempts})...")

    raise SystemExit("OAuth flow timed out after retries")


def google_oauth_exchange(code: str, state: str) -> None:
    manager = GoogleOAuthManager()
    manager.exchange_code(code=code, state=state)
    print("OAuth tokens stored securely in keychain.")


def google_oauth_status() -> None:
    manager = GoogleOAuthManager()
    print(json.dumps(manager.status(), ensure_ascii=True, indent=2))


def run_command(
    workspace_root: Path,
    token: str,
    task: str,
    model: str,
    base_url: str,
    api_key: str,
    system_dna_path: Path,
    interval: float,
    iterations: int,
    connector_refresh_seconds: float,
    connector_refresh_jitter_ratio: float,
) -> None:
    manager = SecurityManager(workspace_root)
    ok, reason = manager.verify(token)
    if not ok:
        raise SystemExit(f"Authentication failed: {reason}")

    system_dna = load_text(system_dna_path)
    client = OpenAI(base_url=base_url, api_key=api_key)
    toolbox = Toolbox(workspace_root=workspace_root)
    runtime = RuntimeStateHandle()
    ipc = SignedLocalIPC(workspace_root)

    runtime_dir = workspace_root / "memory" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    pid_file = runtime_dir / "daemon.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    connector_health_file = runtime_dir / "connector_health.json"

    last_day_map = None
    next_refresh_at = 0.0
    connector_failures = 0

    def _handle_ipc(command: str, payload: dict) -> dict:
        snapshot = runtime.snapshot()
        health_payload = {}
        if connector_health_file.exists():
            try:
                health_payload = json.loads(connector_health_file.read_text(encoding="utf-8"))
                if not isinstance(health_payload, dict):
                    health_payload = {}
            except Exception:
                health_payload = {}

        if command == "status":
            return {
                "ok": True,
                "running": not snapshot.stop_requested,
                "completed_iterations": snapshot.completed_iterations,
                "connector_health": health_payload,
            }
        if command == "stop":
            runtime.request_stop()
            return {"ok": True, "status": "stopping"}
        if command == "quick_voice_trigger":
            runtime.request_quick_voice_trigger()
            return {"ok": True, "status": "queued"}
        if command == "run_once":
            return {"ok": True, "status": "noop"}
        return {"ok": False, "error": f"unknown_command:{command}"}

    ipc_thread = threading.Thread(
        target=ipc.serve,
        args=(_handle_ipc, runtime.should_run),
        daemon=True,
    )
    ipc_thread.start()

    try:
        for i in range(max(1, iterations)):
            if not runtime.should_run():
                break

            if runtime.consume_quick_voice_trigger():
                subprocess.Popen(
                    [
                        "python3",
                        "src/multimodal_orchestrator.py",
                        "--task",
                        "Give me one immediate next action",
                        "--enable-audio",
                        "--enable-transcription",
                        "--consent",
                        "I AGREE",
                    ],
                    cwd=str(workspace_root),
                )

            now = time.time()
            should_refresh = last_day_map is None or now >= next_refresh_at
            if should_refresh:
                refresh_started = time.time()
                try:
                    day_map = build_day_map(workspace_root)
                    last_day_map = day_map
                    connector_failures = 0
                    status = "ok"
                except Exception as exc:
                    connector_failures += 1
                    status = f"error:{exc}"
                    if last_day_map is None:
                        raise
                    day_map = last_day_map

                duration_ms = int((time.time() - refresh_started) * 1000)
                jitter = random.uniform(-connector_refresh_jitter_ratio, connector_refresh_jitter_ratio)
                effective_refresh = max(15.0, connector_refresh_seconds * (1.0 + jitter))
                next_refresh_at = time.time() + effective_refresh

                connector_health = {
                    "last_refresh_utc": datetime.now(timezone.utc).isoformat(),
                    "status": status,
                    "duration_ms": duration_ms,
                    "calendar_items": len(day_map.calendar_items),
                    "task_items": len(day_map.task_items),
                    "consecutive_failures": connector_failures,
                    "next_refresh_in_seconds": int(max(0.0, next_refresh_at - time.time())),
                }
                connector_health_file.write_text(
                    json.dumps(connector_health, ensure_ascii=True, indent=2),
                    encoding="utf-8",
                )
            else:
                day_map = last_day_map

            prompt_context = day_map_to_prompt(day_map)

            output = run_agent_task(
                client=client,
                model=model,
                system_dna=system_dna,
                task_description=task,
                workspace_context="\n\n" + prompt_context,
                toolbox=toolbox,
                allow_tools=False,
                max_tool_steps=1,
            )

            output_file = workspace_root / "memory" / "runtime" / "latest_assistant_output.md"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(output, encoding="utf-8")

            runtime.increment_iterations()
            print(f"Iteration {i + 1}: wrote {output_file.relative_to(workspace_root)}")

            if i + 1 < iterations:
                sleep_steps = int(max(0.2, interval) / 0.2)
                for _ in range(max(1, sleep_steps)):
                    if not runtime.should_run():
                        break
                    time.sleep(0.2)
    finally:
        runtime.request_stop()
        pid_file.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Secure single-user assistant daemon")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--workspace-root", default=os.getenv("AGENT_WORKSPACE_ROOT", "."))

    init_parser = subparsers.add_parser("init", parents=[common], help="Initialize security for one allowed user")
    init_parser.add_argument("--user", required=True)

    add_user_parser = subparsers.add_parser("add-user", parents=[common], help="Allow another OS user")
    add_user_parser.add_argument("--user", required=True)

    subparsers.add_parser("status", parents=[common], help="Show security status")

    consent_parser = subparsers.add_parser("consent", parents=[common], help="Grant or revoke connector consent")
    consent_parser.add_argument("--connector", required=True, choices=["google_calendar", "notion", "todoist"])
    consent_parser.add_argument("--allow", action="store_true")
    consent_parser.add_argument("--revoke", action="store_true")

    google_oauth_begin_parser = subparsers.add_parser("google-oauth-begin", parents=[common], help="Start private Google OAuth flow")
    google_oauth_begin_parser.add_argument("--auto-callback", action="store_true")
    google_oauth_begin_parser.add_argument("--no-open-browser", action="store_true")
    google_oauth_begin_parser.add_argument("--timeout-seconds", type=int, default=180)
    google_oauth_begin_parser.add_argument("--max-attempts", type=int, default=3)

    google_oauth_exchange_parser = subparsers.add_parser("google-oauth-exchange", parents=[common], help="Exchange Google OAuth code for refresh token")
    google_oauth_exchange_parser.add_argument("--code", required=True)
    google_oauth_exchange_parser.add_argument("--state", required=True)

    subparsers.add_parser("google-oauth-status", parents=[common], help="Show Google OAuth token status")

    run_parser = subparsers.add_parser("run", parents=[common], help="Run secure local daemon loop")
    run_parser.add_argument("--token", required=True)
    run_parser.add_argument("--task", default="Generate my next actionable plan from today's calendar and tasks")
    run_parser.add_argument("--model", default=os.getenv("LLM_MODEL", "local-model"))
    run_parser.add_argument("--base-url", default=os.getenv("LLM_BASE_URL", "http://localhost:1234/v1"))
    run_parser.add_argument("--api-key", default=os.getenv("LLM_API_KEY", "lm-studio"))
    run_parser.add_argument("--system-dna", default=os.getenv("AGENT_SYSTEM_DNA", "system_dna.md"))
    run_parser.add_argument("--interval", type=float, default=300.0)
    run_parser.add_argument("--iterations", type=int, default=1)
    run_parser.add_argument("--connector-refresh-seconds", type=float, default=300.0)
    run_parser.add_argument("--connector-refresh-jitter-ratio", type=float, default=0.2)

    args = parser.parse_args()
    workspace_root = Path(args.workspace_root).resolve()

    if args.command == "init":
        init_command(workspace_root, args.user)
        return

    if args.command == "add-user":
        add_user_command(workspace_root, args.user)
        return

    if args.command == "status":
        status_command(workspace_root)
        return

    if args.command == "consent":
        if args.allow == args.revoke:
            raise SystemExit("Specify exactly one of --allow or --revoke")
        consent_command(workspace_root, args.connector, args.allow)
        return

    if args.command == "google-oauth-begin":
        google_oauth_begin(
            auto_capture=args.auto_callback,
            open_browser=not args.no_open_browser,
            timeout_seconds=args.timeout_seconds,
            max_attempts=args.max_attempts,
        )
        return

    if args.command == "google-oauth-exchange":
        google_oauth_exchange(code=args.code, state=args.state)
        return

    if args.command == "google-oauth-status":
        google_oauth_status()
        return

    if args.command == "run":
        system_dna_path = Path(args.system_dna)
        if not system_dna_path.is_absolute():
            system_dna_path = workspace_root / system_dna_path

        run_command(
            workspace_root=workspace_root,
            token=args.token,
            task=args.task,
            model=args.model,
            base_url=args.base_url,
            api_key=args.api_key,
            system_dna_path=system_dna_path,
            interval=args.interval,
            iterations=args.iterations,
            connector_refresh_seconds=args.connector_refresh_seconds,
            connector_refresh_jitter_ratio=args.connector_refresh_jitter_ratio,
        )


if __name__ == "__main__":
    main()
