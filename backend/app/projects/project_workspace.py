import json
import re
from pathlib import Path

from fastapi import HTTPException

from app.core.config import Settings, get_settings
from app.projects.project_diff import read_file_changes, run_root, track_file_change
from app.projects.project_manifest import (
    append_run,
    default_manifest,
    file_type_for,
    manifest_to_snapshot,
    read_manifest,
    upsert_file,
    utc_now,
    write_manifest,
)
from app.projects.project_state import ensure_project_state
from app.projects.schemas import ProjectFile, ProjectFileWriteResult, ProjectManifest, ProjectWorkspace
from app.workspace.safety_policy import resolve_inside


def safe_project_id(project_id: str) -> str:
    normalized = project_id.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,119}", normalized):
        raise HTTPException(status_code=400, detail="project_id must use lowercase letters, numbers, dashes, or underscores.")
    return normalized


class ProjectWorkspaceManager:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = self.settings.project_path
        self.root.mkdir(parents=True, exist_ok=True)

    def get_project_root(self, project_id: str) -> Path:
        return self.root / safe_project_id(project_id)

    def public_root(self, project_id: str) -> str:
        return f"backend/data/projects/{safe_project_id(project_id)}"

    def ensure_project_workspace(self, project_id: str) -> ProjectWorkspace:
        project_root = self.get_project_root(project_id)
        project_root.mkdir(parents=True, exist_ok=True)
        (project_root / "logs").mkdir(exist_ok=True)
        manifest_path = project_root / "manifest.json"
        if not manifest_path.exists() or manifest_path.stat().st_size == 0:
            write_manifest(manifest_path, default_manifest(safe_project_id(project_id)))
        ensure_project_state(project_root / "project_state.md", safe_project_id(project_id))
        history = project_root / "logs" / "project_history.json"
        if not history.exists():
            history.write_text("[]", encoding="utf-8")
        return ProjectWorkspace(
            project_id=safe_project_id(project_id),
            root=self.public_root(project_id),
            state_path="project_state.md",
            manifest_path="manifest.json",
        )

    def resolve(self, project_id: str, relative_path: str, *, allow_directory: bool = False) -> Path:
        return resolve_inside(self.get_project_root(project_id), relative_path, allow_directory=allow_directory)

    def list_project_files(self, project_id: str) -> list[ProjectFile]:
        manifest = self.get_project_manifest(project_id)
        return [
            ProjectFile(
                path=item.path,
                file_type=item.file_type,
                size_bytes=item.size_bytes,
                summary=item.summary,
                updated_at=item.updated_at,
            )
            for item in manifest.files
        ]

    def read_project_file(self, project_id: str, relative_path: str) -> str:
        self.ensure_project_workspace(project_id)
        path = self.resolve(project_id, relative_path)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Project file not found.")
        return path.read_text(encoding="utf-8")

    def write_project_file(
        self,
        project_id: str,
        relative_path: str,
        content: str,
        agent_name: str,
        run_id: str,
        summary: str = "",
    ) -> ProjectFileWriteResult:
        self.ensure_project_workspace(project_id)
        normalized_path = relative_path.replace("\\", "/")
        path = self.resolve(project_id, normalized_path)
        manifest = self.get_project_manifest(project_id)
        existing = next((item for item in manifest.files if item.path == normalized_path), None)
        operation = "updated" if path.exists() else "created"
        before_summary = existing.summary if existing else None
        after_summary = summary or f"{operation.title()} {normalized_path}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        upsert_file(
            manifest,
            relative_path=normalized_path,
            agent_name=agent_name,
            run_id=run_id,
            size_bytes=path.stat().st_size,
            summary=after_summary,
            operation=operation,
        )
        write_manifest(self.get_project_root(project_id) / "manifest.json", manifest)
        change = track_file_change(
            safe_project_id(project_id),
            run_id,
            normalized_path,
            operation,
            before_summary,
            after_summary,
            agent_name,
            self.settings,
        )
        return ProjectFileWriteResult(
            project_id=safe_project_id(project_id),
            path=normalized_path,
            operation=operation,
            agent_name=agent_name,
            run_id=run_id,
            size_bytes=path.stat().st_size,
            before_summary=before_summary,
            after_summary=after_summary,
            timestamp=change.timestamp,
        )

    def get_project_manifest(self, project_id: str) -> ProjectManifest:
        self.ensure_project_workspace(project_id)
        return read_manifest(self.get_project_root(project_id) / "manifest.json", safe_project_id(project_id))

    def save_project_manifest(self, project_id: str, manifest: ProjectManifest) -> None:
        write_manifest(self.get_project_root(project_id) / "manifest.json", manifest)

    def append_project_run(self, project_id: str, run_id: str, summary: str) -> ProjectManifest:
        manifest = self.get_project_manifest(project_id)
        append_run(manifest, run_id=run_id, summary=summary)
        self.save_project_manifest(project_id, manifest)
        self.append_project_history(project_id, {"run_id": run_id, "summary": summary, "created_at": utc_now()})
        return manifest

    def append_project_history(self, project_id: str, event: dict) -> None:
        self.ensure_project_workspace(project_id)
        path = self.get_project_root(project_id) / "logs" / "project_history.json"
        history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        history.append(event)
        path.write_text(json.dumps(history, indent=2), encoding="utf-8")

    def create_run_log_folder(self, run_id: str) -> Path:
        root = run_root(self.settings, run_id)
        for name, default in {
            "timeline.json": "[]",
            "commands.json": "[]",
            "file_changes.json": "[]",
            "workspace_snapshot.json": "{}",
        }.items():
            path = root / name
            if not path.exists():
                path.write_text(default, encoding="utf-8")
        return root

    def write_run_logs(
        self,
        *,
        run_id: str,
        run_summary: dict,
        timeline: list[dict],
        commands: list[dict],
        project_manifest: ProjectManifest,
    ) -> None:
        root = self.create_run_log_folder(run_id)
        (root / "run_summary.json").write_text(json.dumps(run_summary, indent=2, default=str), encoding="utf-8")
        (root / "timeline.json").write_text(json.dumps(timeline, indent=2, default=str), encoding="utf-8")
        (root / "commands.json").write_text(json.dumps(commands, indent=2, default=str), encoding="utf-8")
        (root / "workspace_snapshot.json").write_text(json.dumps(manifest_to_snapshot(project_manifest), indent=2), encoding="utf-8")
        if not (root / "file_changes.json").exists():
            (root / "file_changes.json").write_text(
                json.dumps([item.model_dump() for item in read_file_changes(run_id, self.settings)], indent=2),
                encoding="utf-8",
            )

    def list_projects(self) -> list[dict]:
        projects = []
        if not self.root.exists():
            return projects
        for path in sorted(item for item in self.root.iterdir() if item.is_dir()):
            manifest = read_manifest(path / "manifest.json", path.name)
            projects.append(
                {
                    "project_id": path.name,
                    "root": f"backend/data/projects/{path.name}",
                    "files_count": len(manifest.files),
                    "runs_count": len(manifest.runs),
                    "updated_at": manifest.updated_at,
                }
            )
        return projects

    def project_changes(self, project_id: str) -> list[dict]:
        changes = []
        for run in self.get_project_manifest(project_id).runs:
            changes.extend(item.model_dump() for item in read_file_changes(run.run_id, self.settings))
        return changes
