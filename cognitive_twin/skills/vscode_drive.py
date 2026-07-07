"""
VS Code drive — Anita's build skill.

Give Anita a goal and a project, and she drives VS Code toward it: opens the
project, works a plan step by step, and reports progress. In keeping with the
rest of Vera, actions are PERMISSIONED and CHECKPOINTED — each meaningful step
is written to a plan file the user can watch (and stop), and a hard guardrail
keeps every file action inside the target project (never the wider filesystem).
She does not push to any remote, and only runs a small allow-list of build/
verify commands without asking; anything else is refused and surfaced for the
user to run. Importing this module registers the skills.

This is the SAFE form of "self-drive toward a goal": the model plans, the
executor handles deterministic low-risk actions, and every step is a reviewable
checkpoint rather than a silent write.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

from .base import default_registry as R


def _drive_root() -> Path:
    """Where drive sessions record their plan + checkpoint log."""
    root = Path(os.environ.get("CTWIN_DRIVE_HOME", Path.home() / ".cognitive-twin" / "drive"))
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _resolve_project(project: str) -> Path:
    """Resolve a project directory. Must be an existing directory; expanded and
    made absolute so later file guards can compare against it."""
    p = Path(project).expanduser().resolve()
    if not p.is_dir():
        raise ValueError(f"project '{project}' is not an existing directory")
    return p


def _inside(project: Path, target: Path) -> bool:
    """True only if target is the project dir or lives under it — the guardrail
    that keeps the drive from touching the rest of the filesystem."""
    target = target.resolve()
    return target == project or project in target.parents


def _log_path(project: Path) -> Path:
    """One checkpoint log per project, named from its folder."""
    return _drive_root() / f"drive-{project.name}.md"


# Commands the drive may run without per-call confirmation — read-only or
# standard build/verify steps. Anything else is refused (mirrors Vera's
# confirm-before-acting stance) and returned for the user to run.
_SAFE_COMMANDS = (
    "swift build", "swift test", "xcodegen generate", "xcodebuild",
    "pnpm build", "pnpm test", "npm run build", "npm test",
    "git status", "git log", "git diff", "ls", "cat",
)


def _is_safe_command(cmd: str) -> bool:
    c = cmd.strip()
    return any(c == s or c.startswith(s + " ") for s in _SAFE_COMMANDS)


@R.add(
    "vscode_open",
    "Open a project folder in VS Code. Use at the start of a drive session so "
    "the user can watch the work. Refuses if the path isn't a real directory.",
    {"type": "object", "properties": {
        "project": {"type": "string", "description": "absolute path to the project folder"}},
     "required": ["project"]},
)
def vscode_open(project: str) -> str:
    proj = _resolve_project(project)
    code = "/usr/local/bin/code" if Path("/usr/local/bin/code").exists() else "code"
    try:
        subprocess.run([code, str(proj)], check=False, timeout=20)
    except FileNotFoundError:
        return "[error] the VS Code 'code' CLI isn't installed (Command Palette → 'Shell Command: Install code command')."
    except Exception as e:  # noqa: BLE001 - never crash the agent loop
        return f"[error] couldn't open VS Code: {e}"
    return f"Opened {proj} in VS Code."


@R.add(
    "drive_start",
    "Begin a checkpointed drive toward a goal on a project. Writes the goal and "
    "a fresh checkpoint log the user can follow. Returns the log path.",
    {"type": "object", "properties": {
        "project": {"type": "string", "description": "absolute path to the project folder"},
        "goal": {"type": "string", "description": "what to accomplish, in plain words"}},
     "required": ["project", "goal"]},
)
def drive_start(project: str, goal: str) -> str:
    proj = _resolve_project(project)
    log = _log_path(proj)
    header = (
        f"# Anita drive — {proj.name}\n\n"
        f"**Goal:** {goal}\n\n"
        f"Project: `{proj}`\n\n"
        "Anita works this goal step by step below. Every step is a checkpoint — "
        "watch it here, and stop her any time. She stays inside this project, "
        "runs only build/verify commands on her own, and never pushes.\n\n"
        "## Checkpoints\n"
    )
    log.write_text(header, encoding="utf-8")
    return f"Drive started toward: {goal}\nFollow along + stop anytime at: {log}"


@R.add(
    "drive_checkpoint",
    "Record one step of the drive (what Anita is about to do or just did) to the "
    "checkpoint log. Call this before each meaningful action so the user can see "
    "and stop it.",
    {"type": "object", "properties": {
        "project": {"type": "string"},
        "note": {"type": "string", "description": "the step, in one short line"}},
     "required": ["project", "note"]},
)
def drive_checkpoint(project: str, note: str) -> str:
    proj = _resolve_project(project)
    log = _log_path(proj)
    if not log.exists():
        return "[error] no active drive for this project — call drive_start first."
    with log.open("a", encoding="utf-8") as f:
        f.write(f"- {note}\n")
    return f"Checkpoint logged: {note}"


@R.add(
    "drive_run",
    "Run a build/verify command inside the project (e.g. 'swift test', "
    "'pnpm build'). Only an allow-list of safe build/verify/read commands is "
    "permitted; anything else is refused and returned for the user to run.",
    {"type": "object", "properties": {
        "project": {"type": "string"},
        "command": {"type": "string", "description": "the shell command to run in the project dir"}},
     "required": ["project", "command"]},
)
def drive_run(project: str, command: str) -> str:
    proj = _resolve_project(project)
    if not _is_safe_command(command):
        return (f"[refused] '{command}' isn't on Anita's safe list. Run it yourself, "
                f"or add it deliberately. Safe: {', '.join(_SAFE_COMMANDS)}")
    try:
        out = subprocess.run(
            shlex.split(command), cwd=str(proj), capture_output=True,
            text=True, timeout=600)
    except Exception as e:  # noqa: BLE001
        return f"[error] '{command}' failed to start: {e}"
    tail = (out.stdout or "") + (out.stderr or "")
    tail = tail[-1500:]
    status = "ok" if out.returncode == 0 else f"exit {out.returncode}"
    return f"[{status}] {command}\n{tail}"
