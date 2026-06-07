from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import time
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


def google_oauth_begin(auto_capture: bool) -> None:
    manager = GoogleOAuthManager()
    result = manager.begin_auth()
    print("Open this URL and approve access:")
    print(result["authorization_url"])
    print(f"State: {result['state']}")

    if auto_capture:
        print("Waiting for callback on http://127.0.0.1:8765/callback ...")
        callback = wait_for_oauth_callback()
        code = callback.get("code", "")
        state = callback.get("state", "")
        if not code or not state:
            raise SystemExit("No OAuth callback received before timeout")
        manager.exchange_code(code=code, state=state)
        print("OAuth tokens stored securely in keychain.")


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

    def _handle_ipc(command: str, payload: dict) -> dict:
        snapshot = runtime.snapshot()
        if command == "status":
            return {
                "ok": True,
                "running": not snapshot.stop_requested,
                "completed_iterations": snapshot.completed_iterations,
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

            day_map = build_day_map(workspace_root)
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
        google_oauth_begin(auto_capture=args.auto_callback)
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
        )


if __name__ == "__main__":
    main()
