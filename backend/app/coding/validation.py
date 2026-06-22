from __future__ import annotations

from app.coding.schemas import ProposedPatch, TaskType
from app.core.config import Settings, get_settings
from app.workspace.command_runner import SafeCommandRunner
from app.workspace.schemas import CommandResult


def validation_commands_for_patch(patch: ProposedPatch, task_type: TaskType) -> list[list[str]]:
    requested = []
    for item in patch.validation_commands:
        cmd = item.get("cmd") if isinstance(item, dict) else None
        if isinstance(cmd, list) and all(isinstance(part, str) for part in cmd):
            requested.append(cmd)
    changed = [change.path.replace("\\", "/") for change in patch.files_to_change]
    if any(path == "website/app.py" for path in changed) and ["python", "-m", "py_compile", "website/app.py"] not in requested:
        requested.append(["python", "-m", "py_compile", "website/app.py"])
    for path in changed:
        if path.endswith(".py") and path.startswith("backend/") and ["python", "-m", "py_compile", path] not in requested:
            requested.append(["python", "-m", "py_compile", path])
    if task_type == "frontend_code_change":
        requested.extend([cmd for cmd in [["npm", "run", "lint"], ["npm", "run", "build"]] if cmd not in requested])
    return requested[:4]


def run_validation_commands(
    *,
    project_id: str,
    run_id: str,
    commands: list[list[str]],
    allow_safe_commands: bool,
    settings: Settings | None = None,
) -> list[CommandResult]:
    active_settings = settings or get_settings()
    runner = SafeCommandRunner(active_settings)
    results = []
    for command in commands:
        if allow_safe_commands:
            results.append(runner.run_project_command(project_id, run_id, command))
        else:
            results.append(
                CommandResult(
                    command=command,
                    cwd=".",
                    exit_code=-1,
                    stdout="",
                    stderr="",
                    duration_ms=0,
                    allowed=False,
                    blocked_reason="Blocked by safety policy: safe commands disabled for this run.",
                    executable_command=command,
                )
            )
    return results
