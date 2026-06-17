import json
from pathlib import Path

from fastapi import HTTPException

from app.core.config import Settings, get_settings
from app.workspace.schemas import CommandResult, WorkspaceManifest
from app.workspace.safety_policy import resolve_inside


class WorkspaceManager:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = self.settings.workspace_path
        self.root.mkdir(parents=True, exist_ok=True)

    def workspace_root(self, run_id: str) -> Path:
        safe_run_id = run_id.replace("/", "_").replace("\\", "_")
        root = self.root / safe_run_id
        root.mkdir(parents=True, exist_ok=True)
        (root / "generated").mkdir(exist_ok=True)
        (root / "logs").mkdir(exist_ok=True)
        if not (root / "manifest.json").exists():
            (root / "manifest.json").write_text(WorkspaceManifest(run_id=run_id).model_dump_json(indent=2), encoding="utf-8")
        if not (root / "logs" / "commands.json").exists():
            (root / "logs" / "commands.json").write_text("[]", encoding="utf-8")
        return root

    def public_root(self, run_id: str) -> str:
        return f"backend/data/workspaces/{run_id}"

    def resolve(self, run_id: str, relative_path: str, *, allow_directory: bool = False) -> Path:
        return resolve_inside(self.workspace_root(run_id), relative_path, allow_directory=allow_directory)

    def read_manifest(self, run_id: str) -> WorkspaceManifest:
        manifest_path = self.workspace_root(run_id) / "manifest.json"
        if not manifest_path.exists():
            return WorkspaceManifest(run_id=run_id)
        return WorkspaceManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))

    def write_manifest(self, run_id: str, manifest: WorkspaceManifest) -> None:
        path = self.workspace_root(run_id) / "manifest.json"
        path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    def read_commands(self, run_id: str) -> list[CommandResult]:
        path = self.workspace_root(run_id) / "logs" / "commands.json"
        if not path.exists():
            return []
        return [CommandResult.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]

    def append_command(self, run_id: str, result: CommandResult) -> None:
        commands = self.read_commands(run_id)
        commands.append(result)
        path = self.workspace_root(run_id) / "logs" / "commands.json"
        path.write_text(json.dumps([command.model_dump() for command in commands], indent=2), encoding="utf-8")

    def read_workspace_file(self, run_id: str, relative_path: str) -> str:
        path = self.resolve(run_id, relative_path)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Workspace file not found.")
        return path.read_text(encoding="utf-8")
