from datetime import UTC, datetime

from app.core.config import Settings
from app.workspace.schemas import FileManifestEntry, WorkspaceManifest
from app.workspace.workspace_manager import WorkspaceManager


class WorkspaceFileWriter:
    def __init__(self, settings: Settings | None = None) -> None:
        self.manager = WorkspaceManager(settings)

    def write_file(self, run_id: str, relative_path: str, content: str, agent_name: str, summary: str = "") -> FileManifestEntry:
        path = self.manager.resolve(run_id, relative_path)
        operation = "updated" if path.exists() else "created"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        entry = FileManifestEntry(
            path=relative_path.replace("\\", "/"),
            agent_name=agent_name,
            timestamp=datetime.now(UTC).isoformat(),
            size_bytes=path.stat().st_size,
            summary=summary or f"{operation.title()} {relative_path}",
            operation=operation,
        )
        manifest = self.manager.read_manifest(run_id)
        manifest.files = [item for item in manifest.files if item.path != entry.path]
        manifest.files.append(entry)
        self.manager.write_manifest(run_id, WorkspaceManifest(run_id=run_id, files=manifest.files))
        return entry

    def read_file(self, run_id: str, relative_path: str) -> str:
        return self.manager.read_workspace_file(run_id, relative_path)

    def list_files(self, run_id: str) -> list[str]:
        return [entry.path for entry in self.manager.read_manifest(run_id).files]

    def get_file_manifest(self, run_id: str) -> WorkspaceManifest:
        return self.manager.read_manifest(run_id)
