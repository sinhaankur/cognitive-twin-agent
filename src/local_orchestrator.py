import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from openai import OpenAI


def load_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def is_within(root: Path, target: Path) -> bool:
    root_resolved = root.resolve()
    target_resolved = target.resolve()
    return str(target_resolved).startswith(str(root_resolved))


class Toolbox:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()

    def _resolve(self, relative_path: str) -> Path:
        candidate = (self.workspace_root / relative_path).resolve()
        if not is_within(self.workspace_root, candidate):
            raise ValueError("Path escapes workspace root")
        return candidate

    def read_file(self, relative_path: str, max_chars: int = 12000) -> dict[str, Any]:
        path = self._resolve(relative_path)
        if not path.exists() or not path.is_file():
            return {"ok": False, "error": "File not found"}

        content = load_text(path)
        truncated = content[:max_chars]
        return {
            "ok": True,
            "path": relative_path,
            "truncated": len(content) > max_chars,
            "content": truncated,
        }

    def write_file(self, relative_path: str, content: str, append: bool = False) -> dict[str, Any]:
        path = self._resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with path.open(mode, encoding="utf-8") as f:
            f.write(content)
        return {"ok": True, "path": relative_path, "bytes_written": len(content.encode("utf-8"))}

    def list_files(self, pattern: str = "**/*", limit: int = 100) -> dict[str, Any]:
        matches = []
        for p in self.workspace_root.glob(pattern):
            if p.is_file():
                matches.append(str(p.relative_to(self.workspace_root)))
            if len(matches) >= limit:
                break
        return {"ok": True, "count": len(matches), "files": matches}

    def run_command(self, command: str, timeout: int = 30) -> dict[str, Any]:
        # Prevent obviously dangerous shell sequences in this starter runtime.
        blocked_tokens = ["rm -rf", "mkfs", "shutdown", "reboot", ":(){", "dd if="]
        lowered = command.lower()
        if any(token in lowered for token in blocked_tokens):
            return {"ok": False, "error": "Blocked potentially destructive command"}

        result = subprocess.run(
            command,
            shell=True,
            cwd=str(self.workspace_root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout[-12000:],
            "stderr": result.stderr[-6000:],
        }


def parse_tool_request(text: str) -> dict[str, Any] | None:
    payload = text.strip()
    if payload.startswith("```"):
        lines = payload.splitlines()
        if len(lines) >= 3:
            payload = "\n".join(lines[1:-1]).strip()

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None

    if "tool" not in parsed:
        return None

    return parsed


def run_agent_task(
    client: OpenAI,
    model: str,
    system_dna: str,
    task_description: str,
    workspace_context: str,
    toolbox: Toolbox,
    allow_tools: bool,
    max_tool_steps: int,
) -> str:
    tool_protocol = ""
    if allow_tools:
        tool_protocol = (
            "\n\n# TOOL PROTOCOL\n"
            "If a tool is needed, respond ONLY with strict JSON:\n"
            '{"tool":"read_file|write_file|list_files|run_command","args":{...}}\n'
            "When no tool is needed, provide the final answer in plain text."
        )

    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": system_dna + workspace_context + tool_protocol,
        },
        {
            "role": "user",
            "content": task_description,
        },
    ]

    final_answer = ""

    for _ in range(max(1, max_tool_steps)):
        response = client.chat.completions.create(
            model=model,
            temperature=0.2,
            messages=messages,
        )
        content = response.choices[0].message.content or ""
        final_answer = content

        if not allow_tools:
            break

        request = parse_tool_request(content)
        if request is None:
            break

        tool_name = request.get("tool")
        args = request.get("args", {})
        if not isinstance(args, dict):
            args = {}

        try:
            if tool_name == "read_file":
                result = toolbox.read_file(**args)
            elif tool_name == "write_file":
                result = toolbox.write_file(**args)
            elif tool_name == "list_files":
                result = toolbox.list_files(**args)
            elif tool_name == "run_command":
                result = toolbox.run_command(**args)
            else:
                result = {"ok": False, "error": f"Unknown tool: {tool_name}"}
        except Exception as exc:  # pragma: no cover - defensive guard
            result = {"ok": False, "error": str(exc)}

        messages.append({"role": "assistant", "content": content})
        messages.append(
            {
                "role": "user",
                "content": "TOOL_RESULT\n" + json.dumps(result, ensure_ascii=True),
            }
        )

    return final_answer


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Cognitive Twin Orchestrator")
    parser.add_argument("--task", help="Task description for the agent")
    parser.add_argument("--context", help="Optional context file path", default=None)
    parser.add_argument("--workspace-root", default=os.getenv("AGENT_WORKSPACE_ROOT", "."))
    parser.add_argument("--system-dna", default=os.getenv("AGENT_SYSTEM_DNA", "system_dna.md"))
    parser.add_argument("--model", default=os.getenv("LLM_MODEL", "local-model"))
    parser.add_argument("--base-url", default=os.getenv("LLM_BASE_URL", "http://localhost:1234/v1"))
    parser.add_argument("--api-key", default=os.getenv("LLM_API_KEY", "lm-studio"))
    parser.add_argument("--allow-tools", action="store_true")
    parser.add_argument(
        "--max-tool-steps",
        type=int,
        default=int(os.getenv("AGENT_MAX_TOOL_STEPS", "4")),
    )
    args = parser.parse_args()

    task = args.task
    if not task:
        task = input("Task> ").strip()

    if not task:
        raise SystemExit("No task provided")

    workspace_root = Path(args.workspace_root)
    system_dna_path = Path(args.system_dna)
    if not system_dna_path.is_absolute():
        system_dna_path = workspace_root / system_dna_path

    system_dna = load_text(system_dna_path)

    workspace_context = ""
    if args.context:
        context_path = Path(args.context)
        if not context_path.is_absolute():
            context_path = workspace_root / context_path
        if context_path.exists() and context_path.is_file():
            workspace_context = "\n\n# CURRENT PROJECT CONTEXT\n" + load_text(context_path)

    client = OpenAI(base_url=args.base_url, api_key=args.api_key)
    toolbox = Toolbox(workspace_root=workspace_root)

    output = run_agent_task(
        client=client,
        model=args.model,
        system_dna=system_dna,
        task_description=task,
        workspace_context=workspace_context,
        toolbox=toolbox,
        allow_tools=args.allow_tools,
        max_tool_steps=args.max_tool_steps,
    )

    print(output)


if __name__ == "__main__":
    main()
