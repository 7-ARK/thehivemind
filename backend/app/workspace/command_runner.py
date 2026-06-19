import subprocess
import sys
import time
import json
import traceback
from pathlib import Path

from app.core.config import Settings
from app.projects.project_diff import run_root
from app.projects.project_workspace import ProjectWorkspaceManager
from app.workspace.safety_policy import resolve_inside, validate_command, validate_relative_path
from app.workspace.schemas import CommandResult
from app.workspace.workspace_manager import WorkspaceManager


class SafeCommandRunner:
    def __init__(self, settings: Settings | None = None, timeout_seconds: int = 30) -> None:
        self.manager = WorkspaceManager(settings)
        self.timeout_seconds = timeout_seconds

    def run_safe_command(self, run_id: str, command: list[str], cwd: str | None = None) -> CommandResult:
        workspace_root = self.manager.workspace_root(run_id)
        command_cwd = resolve_inside(workspace_root, cwd or ".", allow_directory=True)
        result = self._run_validated_command(root=workspace_root, command_cwd=command_cwd, command=command)
        self.manager.append_command(run_id, result)
        return result

    def run_project_command(self, project_id: str, run_id: str, command: list[str], cwd: str | None = None) -> CommandResult:
        project_manager = ProjectWorkspaceManager(self.manager.settings)
        project_manager.ensure_project_workspace(project_id)
        project_root = project_manager.get_project_root(project_id)
        command_cwd = resolve_inside(project_root, cwd or ".", allow_directory=True)
        result = self._run_validated_command(root=project_root, command_cwd=command_cwd, command=command)
        self._append_run_command(run_id, result)
        project_manager.append_project_history(
            project_id,
            {
                "run_id": run_id,
                "event": "command",
                "command": result.command,
                "exit_code": result.exit_code,
                "allowed": result.allowed,
                "timestamp": time.time(),
            },
        )
        return result

    def _run_validated_command(self, *, root: Path, command_cwd: Path, command: list[str]) -> CommandResult:
        command_cwd.mkdir(parents=True, exist_ok=True)
        allowed, reason = validate_command(command)
        if allowed:
            allowed, reason = self._validate_command_arguments(command)
        if not allowed:
            return CommandResult(
                command=command,
                cwd=str(command_cwd.relative_to(root)),
                exit_code=-1,
                stdout="",
                stderr="",
                duration_ms=0,
                allowed=False,
                blocked_reason=reason,
                executable_command=command,
                resolved_cwd=str(command_cwd),
            )

        start = time.perf_counter()
        executable_command = self._executable_command(command)
        try:
            completed = subprocess.run(
                executable_command,
                cwd=command_cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                shell=False,
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
            result = CommandResult(
                command=command,
                cwd=str(command_cwd.relative_to(root)),
                exit_code=completed.returncode,
                stdout=completed.stdout[-4000:],
                stderr=completed.stderr[-4000:],
                duration_ms=duration_ms,
                allowed=True,
                executable_command=executable_command,
                resolved_cwd=str(command_cwd),
                error_type=_classify_process_error(command, completed.stderr, completed.returncode) if completed.returncode != 0 else None,
                error_message=f"Command exited with code {completed.returncode}." if completed.returncode != 0 else None,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            result = CommandResult(
                command=command,
                cwd=str(command_cwd.relative_to(root)),
                exit_code=124,
                stdout=(exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
                stderr=(exc.stderr or "Command timed out.")[-4000:] if isinstance(exc.stderr, str) else "Command timed out.",
                duration_ms=duration_ms,
                allowed=True,
                executable_command=executable_command,
                resolved_cwd=str(command_cwd),
                error_type="timeout",
                error_message=f"Command timed out after {self.timeout_seconds} seconds.",
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            result = CommandResult(
                command=command,
                cwd=str(command_cwd.relative_to(root)),
                exit_code=1,
                stdout="",
                stderr=traceback.format_exc()[-4000:],
                duration_ms=duration_ms,
                allowed=True,
                executable_command=executable_command,
                resolved_cwd=str(command_cwd),
                error_type="environment_error",
                error_message=str(exc),
            )
        return result

    def _append_run_command(self, run_id: str, result: CommandResult) -> None:
        path = run_root(self.manager.settings, run_id) / "commands.json"
        commands = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        commands.append(result.model_dump())
        path.write_text(json.dumps(commands, indent=2), encoding="utf-8")

    def _executable_command(self, command: list[str]) -> list[str]:
        if command and command[0].lower() == "python":
            return [sys.executable, *command[1:]]
        return command

    def _validate_command_arguments(self, command: list[str]) -> tuple[bool, str | None]:
        lowered = [part.lower() for part in command]
        if lowered[:3] == ["python", "-m", "py_compile"]:
            for argument in command[3:]:
                if argument.startswith("-"):
                    continue
                try:
                    validate_relative_path(argument)
                except Exception:
                    return False, "py_compile file arguments must be safe workspace-relative paths."
        return True, None


def _classify_process_error(command: list[str], stderr: str, returncode: int) -> str:
    lowered = stderr.lower()
    if "keyboardinterrupt" in lowered or "watchfiles" in lowered or "runtime error" in lowered or returncode in {3221225786, -1073741510}:
        return "environment_interruption"
    if [part.lower() for part in command[:3]] == ["python", "-m", "py_compile"]:
        return "validation_error"
    return "command_runtime_error"
