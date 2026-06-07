from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from openai import OpenAI

from day_mapper import build_day_map, day_map_to_prompt
from local_orchestrator import load_text, run_agent_task, Toolbox
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

    for i in range(max(1, iterations)):
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

        print(f"Iteration {i + 1}: wrote {output_file.relative_to(workspace_root)}")

        if i + 1 < iterations:
            time.sleep(max(0.2, interval))


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
