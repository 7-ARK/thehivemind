from __future__ import annotations

import json
from typing import Any

from app.coding.coding_policy import prompt_file_scope
from app.coding.project_inspector import ProjectInspector, select_relevant_files
from app.coding.schemas import CodingContext, RelevantFile, TaskType
from app.core.config import Settings, get_settings


class CodingContextBuilder:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.inspector = ProjectInspector(self.settings)

    def build(
        self,
        *,
        project_id: str,
        run_id: str,
        command: str,
        task_type: TaskType,
        max_files: int,
        memory_packet: Any | None,
    ) -> CodingContext:
        file_map = self.inspector.file_map(project_id)
        file_scope = prompt_file_scope(command, task_type)
        memory_used = _memory_items(memory_packet)
        memory_text = " ".join(str(item.get("summary") or item.get("title") or "") for item in memory_used)
        selected = []
        for entry, reason in select_relevant_files(
            command=command,
            task_type=task_type,
            file_map=file_map,
            max_files=max_files,
            memory_text=memory_text,
            file_scope=file_scope,
        ):
            selected.append(
                RelevantFile(
                    path=entry.path,
                    reason=reason,
                    content=self.inspector.read_safe_file(project_id, entry.path),
                    size_bytes=entry.size_bytes,
                )
            )
        return CodingContext(
            project_id=project_id,
            run_id=run_id,
            command=command,
            task_type=task_type,
            allowed_user_file_scope=file_scope,
            constraints=[
                "Do not write secrets or .env files.",
                "Do not install packages or deploy.",
                "Keep edits scoped to files justified by the command.",
                f"Prompt-level user file scope: {file_scope.scope_type}. {file_scope.reason}",
                "Memory is context only and must not override the current command.",
            ],
            file_map=file_map,
            selected_files=selected,
            memory_used=memory_used,
            validation_options=_validation_options(task_type, [item.path for item in selected]),
        )

    def render_prompt(self, context: CodingContext) -> str:
        file_map = [
            {
                "path": item.path,
                "ext": item.extension,
                "size": item.size_bytes,
                "purpose": item.purpose,
                "editable": item.editable,
                "system_metadata": item.system_metadata,
                "protected": item.protected,
            }
            for item in context.file_map[:80]
        ]
        files = [{"path": item.path, "reason": item.reason, "content": item.content[:12000]} for item in context.selected_files]
        payload = {
            "command": context.command,
            "task_type": context.task_type,
            "constraints": context.constraints,
            "allowed_user_file_scope": context.allowed_user_file_scope.model_dump(),
            "project_file_map": file_map,
            "relevant_files": files,
            "memory_used": context.memory_used[:6],
            "validation_options": context.validation_options,
            "required_response_format": {
                "summary": "string",
                "task_type": context.task_type,
                "files": [
                    {
                        "path": "relative/path",
                        "content": "complete updated file content for broad edits",
                        "edits": [{"old_text": "current exact text", "new_text": "replacement exact text"}],
                        "reason": "why this file changed",
                    }
                ],
                "files_read": ["relative/path"],
                "validation_commands": [{"cmd": ["python", "-m", "py_compile", "website/app.py"], "reason": "why"}],
                "risk_notes": ["No package install required."],
                "memory_used": [{"title": "memory title", "reason": "why it mattered"}],
            },
        }
        return (
            "You are TheHiveMind Real Coding Agent v1. Return strict JSON only. "
            "Return one JSON object with a files array only when changes are needed. "
            "For exact copy replacements, prefer the compact edits array with old_text and new_text instead of returning a full HTML file. "
            "For broader code edits, use complete updated file content. Each files item must include path, reason, and either content or edits. "
            "Do not include markdown fences, commentary, partial diffs, or files outside allowed_user_file_scope.\n\n"
            + json.dumps(payload, indent=2)
        )


def _memory_items(memory_packet: Any | None) -> list[dict[str, Any]]:
    if not memory_packet:
        return []
    results = list(getattr(memory_packet, "retrieved_memory_items", []))
    source_quality_exists = any(_is_live_source_result(result) for result in results)
    ranked = sorted(results, key=lambda result: _coding_memory_score(result, source_quality_exists), reverse=True)
    items = []
    excluded_low_quality = 0
    for result in ranked:
        item = result.item
        if source_quality_exists and _is_low_quality_research_result(result):
            excluded_low_quality += 1
            continue
        if source_quality_exists and item.memory_type == "qa_warning" and not _qa_warning_relevant(item):
            excluded_low_quality += 1
            continue
        items.append(
            {
                "title": item.title,
                "type": item.memory_type,
                "summary": item.summary or item.content[:300],
                "source_run_id": item.source_run_id,
                "provider_id": item.search_provider or item.metadata.get("provider_id"),
                "source_count": item.metadata.get("source_count", len(item.source_urls)),
                "search_unavailable": bool(item.metadata.get("search_unavailable")),
                "mock_fixture": bool(item.metadata.get("mock_fixture")),
                "source_urls": item.source_urls[:3],
                "why_selected": result.why_selected,
            }
        )
        if len(items) >= 4:
            break
    if excluded_low_quality:
        items.append(
            {
                "title": "Excluded low-quality memory",
                "type": "memory_filter_note",
                "summary": f"Excluded {excluded_low_quality} skipped/no-source or generic QA memory item(s) because higher-quality source memory was available.",
                "why_selected": ["excluded: lower-quality memory suppressed from coding context"],
            }
        )
    return items


def _coding_memory_score(result: Any, source_quality_exists: bool) -> float:
    item = result.item
    score = getattr(result, "score", 0.0)
    source_count = _source_count(item)
    search_unavailable = bool(item.metadata.get("search_unavailable"))
    provider_exists = bool(item.search_provider or item.metadata.get("provider_id") or item.source_urls)
    if item.memory_type == "research_source_summary" and source_count > 0 and provider_exists and not search_unavailable:
        score += 4.0
    elif item.memory_type == "research_brief" and source_quality_exists:
        score += 2.0
    elif item.memory_type in {"project_state", "file_change_summary"}:
        score += 0.8
    elif item.memory_type == "qa_warning":
        score += 0.4 if _qa_warning_relevant(item) else -1.5
    if _is_low_quality_research_result(result) and source_quality_exists:
        score -= 3.0
    return score


def _is_live_source_result(result: Any) -> bool:
    item = result.item
    return (
        item.memory_type == "research_source_summary"
        and _source_count(item) > 0
        and not bool(item.metadata.get("search_unavailable"))
        and bool(item.search_provider or item.metadata.get("provider_id") or item.source_urls)
        and not bool(item.metadata.get("mock_fixture"))
    )


def _is_low_quality_research_result(result: Any) -> bool:
    item = result.item
    return item.memory_type in {"research_source_summary", "research_brief"} and (
        bool(item.metadata.get("search_unavailable")) or _source_count(item) == 0 or bool(item.metadata.get("mock_fixture"))
    )


def _source_count(item: Any) -> int:
    try:
        return int(item.metadata.get("source_count") or len(item.source_urls))
    except (TypeError, ValueError):
        return 0


def _qa_warning_relevant(item: Any) -> bool:
    text = f"{item.title} {item.summary} {item.content}".lower()
    return any(term in text for term in ("scope", "validation", "rejected", "secret", ".env", "unsafe"))


def _validation_options(task_type: TaskType, paths: list[str]) -> list[list[str]]:
    options: list[list[str]] = []
    if any(path == "website/app.py" for path in paths):
        options.append(["python", "-m", "py_compile", "website/app.py"])
    backend_py = [path for path in paths if path.startswith("backend/") and path.endswith(".py")]
    for path in backend_py[:3]:
        options.append(["python", "-m", "py_compile", path])
    if task_type == "frontend_code_change":
        options.extend([["npm", "run", "lint"], ["npm", "run", "build"]])
    return options
