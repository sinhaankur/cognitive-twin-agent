from dataclasses import dataclass

from local_orchestrator import Toolbox
from multimodal_types import FusedState


@dataclass
class SafeAction:
    action_id: str
    description: str
    command: str
    rollback_command: str


def recommend_safe_action(state: FusedState) -> SafeAction:
    if state.user_state == "fatigued":
        return SafeAction(
            action_id="reset-break",
            description="Create a short reset note to enforce a 5-minute recovery break.",
            command='mkdir -p memory/actions && printf "Take 5 minutes away from screen.\\nReturn with one concrete next step.\\n" > memory/actions/next_action.md',
            rollback_command='rm -f memory/actions/next_action.md',
        )

    if state.stress_state == "elevated":
        return SafeAction(
            action_id="scope-trim",
            description="Create a scope-trim checklist to reduce cognitive load.",
            command='mkdir -p memory/actions && printf "1) Stop current branch of work\\n2) Pick one subtask\\n3) Ship smallest reversible change\\n" > memory/actions/next_action.md',
            rollback_command='rm -f memory/actions/next_action.md',
        )

    return SafeAction(
        action_id="focus-plan",
        description="Create a focused 30-minute action note.",
        command='mkdir -p memory/actions && printf "Focus block: 30 minutes\\nGoal: deliver one completed subtask\\n" > memory/actions/next_action.md',
        rollback_command='rm -f memory/actions/next_action.md',
    )


def execute_safe_action(toolbox: Toolbox, action: SafeAction, approved: bool) -> dict:
    if not approved:
        return {
            "ok": False,
            "status": "pending_approval",
            "action_id": action.action_id,
            "description": action.description,
            "command": action.command,
            "rollback_command": action.rollback_command,
        }

    execution = toolbox.run_command(action.command, timeout=10)
    result = {
        "ok": execution.get("ok", False),
        "status": "executed" if execution.get("ok", False) else "failed",
        "action_id": action.action_id,
        "description": action.description,
        "command": action.command,
        "rollback_command": action.rollback_command,
        "execution": execution,
    }
    return result
