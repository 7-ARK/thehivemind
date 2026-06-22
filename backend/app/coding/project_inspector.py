from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.coding.coding_policy import TEXT_EXTENSIONS, allowed_by_prompt_scope, allowed_for_task, is_protected_path, is_system_metadata
from app.coding.schemas import AllowedUserFileScope, ProjectFileMapEntry, TaskType
from app.core.config import Settings, get_settings
from app.projects.project_workspace import ProjectWorkspaceManager


MAX_READ_FILE_BYTES = 80_000


class ProjectInspector:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.manager = ProjectWorkspaceManager(self.settings)

    def file_map(self, project_id: str) -> list[ProjectFileMapEntry]:
        self.manager.ensure_project_workspace(project_id)
        root = self.manager.get_project_root(project_id)
        entries: list[ProjectFileMapEntry] = []
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = path.relative_to(root).as_posix()
            protected, reason = is_protected_path(relative)
            suffix = path.suffix.lower()
            binary = suffix not in TEXT_EXTENSIONS
            too_large = path.stat().st_size > MAX_READ_FILE_BYTES
            entries.append(
                ProjectFileMapEntry(
                    path=relative,
                    extension=suffix,
                    size_bytes=path.stat().st_size,
                    last_modified=datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
                    purpose=_purpose(relative),
                    editable=not protected and not binary and not too_large and not is_system_metadata(relative),
                    system_metadata=is_system_metadata(relative),
                    protected=protected,
                    binary=binary,
                    too_large=too_large,
                    reason=reason,
                )
            )
        return entries

    def read_safe_file(self, project_id: str, relative_path: str) -> str:
        entry_path = relative_path.replace("\\", "/")
        protected, reason = is_protected_path(entry_path)
        if protected:
            raise ValueError(reason)
        path = self.manager.resolve(project_id, entry_path)
        if not path.exists() or not path.is_file():
            return ""
        if path.stat().st_size > MAX_READ_FILE_BYTES:
            raise ValueError("File is too large for Real Coding Agent context.")
        return path.read_text(encoding="utf-8")


def select_relevant_files(
    *,
    command: str,
    task_type: TaskType,
    file_map: list[ProjectFileMapEntry],
    max_files: int,
    memory_text: str = "",
    file_scope: AllowedUserFileScope | None = None,
) -> list[tuple[ProjectFileMapEntry, str]]:
    terms = _terms(command + " " + memory_text)
    scored: list[tuple[float, ProjectFileMapEntry, str]] = []
    for entry in file_map:
        if not entry.editable:
            continue
        allowed, reason = allowed_for_task(entry.path, task_type)
        if not allowed:
            continue
        if file_scope:
            scoped, _scope_reason = allowed_by_prompt_scope(entry.path, file_scope)
            if not scoped:
                continue
        score = _task_path_score(entry.path, task_type)
        path_terms = set(_terms(entry.path.replace("/", " ").replace("_", " ").replace("-", " ")))
        overlap = len(terms & path_terms)
        score += overlap * 2
        if entry.path.lower() in command.lower():
            score += 10
        if entry.path.endswith(("README.md", "index.html", "status.html", "app.py")):
            score += 1
        if score > 0:
            scored.append((score, entry, reason or "Relevant to command and task type."))
    ranked = sorted(scored, key=lambda item: (item[0], -item[1].size_bytes), reverse=True)
    return [(entry, _selection_reason(entry.path, task_type, score)) for score, entry, _reason in ranked[:max_files]]


def _purpose(path: str) -> str:
    if path.endswith("index.html"):
        return "homepage/template"
    if path.endswith("status.html"):
        return "status page template"
    if path.endswith("app.py"):
        return "python app/backend file"
    if path.endswith(".json"):
        return "structured data/config"
    if path.endswith(".md"):
        return "documentation/project state"
    if path.endswith((".tsx", ".ts")):
        return "frontend source"
    return "project file"


def _task_path_score(path: str, task_type: TaskType) -> float:
    lowered = path.lower()
    if task_type == "website_copy_update":
        if lowered.endswith("index.html"):
            return 12
        if "faq" in lowered or lowered.endswith("faqs.json"):
            return 8
        if lowered.endswith("readme.md"):
            return 4
    if task_type == "website_ui_update":
        if lowered.endswith((".html", ".css")):
            return 10
        if lowered.endswith(".py"):
            return 4
    if task_type == "backend_code_change" and lowered.endswith(".py"):
        return 10
    if task_type == "frontend_code_change" and lowered.endswith((".tsx", ".ts", ".css")):
        return 10
    if task_type == "documentation_update" and lowered.endswith(".md"):
        return 10
    if task_type == "data_content_update" and lowered.endswith((".json", ".md", ".html")):
        return 8
    if task_type == "bug_fix":
        return 3
    return 1


def _terms(text: str) -> set[str]:
    return {part for part in "".join(ch if ch.isalnum() else " " for ch in text.lower()).split() if len(part) > 2}


def _selection_reason(path: str, task_type: TaskType, score: float) -> str:
    return f"Selected for {task_type}; relevance score {score:.1f}; path {path}."
