import json
from datetime import UTC, datetime
from pathlib import Path

from app.projects.schemas import ProjectManifest, ProjectManifestFile, ProjectRunEntry


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def file_type_for(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript-react",
        ".js": "javascript",
        ".jsx": "javascript-react",
        ".json": "json",
        ".md": "markdown",
        ".txt": "text",
        ".html": "html",
        ".css": "css",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".toml": "toml",
    }.get(suffix, suffix.lstrip(".") or "unknown")


def default_manifest(project_id: str) -> ProjectManifest:
    now = utc_now()
    return ProjectManifest(project_id=project_id, created_at=now, updated_at=now)


def read_manifest(path: Path, project_id: str) -> ProjectManifest:
    if not path.exists():
        return default_manifest(project_id)
    return ProjectManifest.model_validate_json(path.read_text(encoding="utf-8"))


def write_manifest(path: Path, manifest: ProjectManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")


def upsert_file(
    manifest: ProjectManifest,
    *,
    relative_path: str,
    agent_name: str,
    run_id: str,
    size_bytes: int,
    summary: str,
    operation: str,
) -> ProjectManifestFile:
    now = utc_now()
    existing = next((item for item in manifest.files if item.path == relative_path), None)
    entry = ProjectManifestFile(
        path=relative_path,
        created_at=existing.created_at if existing else now,
        updated_at=now,
        created_by=existing.created_by if existing else agent_name,
        last_modified_by=agent_name,
        last_run_id=run_id,
        file_type=file_type_for(relative_path),
        size_bytes=size_bytes,
        summary=summary,
    )
    manifest.files = [item for item in manifest.files if item.path != relative_path]
    manifest.files.append(entry)
    manifest.files.sort(key=lambda item: item.path)
    manifest.updated_at = now
    return entry


def append_run(manifest: ProjectManifest, *, run_id: str, summary: str) -> None:
    if any(item.run_id == run_id for item in manifest.runs):
        return
    manifest.runs.append(ProjectRunEntry(run_id=run_id, summary=summary, created_at=utc_now()))
    manifest.updated_at = utc_now()


def manifest_to_snapshot(manifest: ProjectManifest) -> dict:
    return json.loads(manifest.model_dump_json())
