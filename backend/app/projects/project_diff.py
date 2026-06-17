import json
from pathlib import Path

from app.core.config import Settings, get_settings
from app.projects.project_manifest import utc_now
from app.projects.schemas import FileChange


def run_root(settings: Settings, run_id: str) -> Path:
    safe_run_id = run_id.replace("/", "_").replace("\\", "_")
    root = settings.run_path / safe_run_id
    root.mkdir(parents=True, exist_ok=True)
    (root / "artifacts").mkdir(exist_ok=True)
    return root


def read_file_changes(run_id: str, settings: Settings | None = None) -> list[FileChange]:
    active_settings = settings or get_settings()
    path = run_root(active_settings, run_id) / "file_changes.json"
    if not path.exists():
        return []
    return [FileChange.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]


def track_file_change(
    project_id: str,
    run_id: str,
    path: str,
    operation: str,
    before_summary: str | None,
    after_summary: str,
    agent_name: str,
    settings: Settings | None = None,
) -> FileChange:
    active_settings = settings or get_settings()
    change = FileChange(
        project_id=project_id,
        run_id=run_id,
        path=path,
        operation=operation,
        agent_name=agent_name,
        before_summary=before_summary,
        after_summary=after_summary,
        timestamp=utc_now(),
    )
    changes = read_file_changes(run_id, active_settings)
    changes.append(change)
    target = run_root(active_settings, run_id) / "file_changes.json"
    target.write_text(json.dumps([item.model_dump() for item in changes], indent=2), encoding="utf-8")
    return change
