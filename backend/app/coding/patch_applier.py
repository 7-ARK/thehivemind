from __future__ import annotations

import difflib
from app.coding.coding_policy import allowed_by_prompt_scope, allowed_for_task, contains_secret_like_text, is_protected_path
from app.coding.schemas import AllowedUserFileScope, AppliedPatchFile, PatchValidationResult, ProposedPatch, TaskType
from app.core.config import Settings, get_settings
from app.projects.project_workspace import ProjectWorkspaceManager
from app.projects.schemas import ProjectFileWriteResult


class PatchApplier:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.manager = ProjectWorkspaceManager(self.settings)

    def validate(
        self,
        patch: ProposedPatch,
        *,
        task_type: TaskType,
        file_scope: AllowedUserFileScope | None = None,
        max_output_files: int | None = None,
        project_id: str | None = None,
    ) -> PatchValidationResult:
        violations: list[str] = []
        warnings: list[str] = []
        output_limit = max_output_files or self.settings.real_coding_max_output_files
        if len(patch.files_to_change) > output_limit:
            violations.append(f"Too many output files: {len(patch.files_to_change)} > {output_limit}.")
        total_bytes = sum(len((change.new_content or "").encode("utf-8")) + sum(len(edit.new_text.encode("utf-8")) for edit in change.edits) for change in patch.files_to_change)
        if total_bytes > self.settings.real_coding_max_patch_bytes:
            violations.append(f"Patch bytes exceed REAL_CODING_MAX_PATCH_BYTES={self.settings.real_coding_max_patch_bytes}.")
        seen = set()
        for change in patch.files_to_change:
            path = change.path.replace("\\", "/")
            if path in seen:
                violations.append(f"Duplicate file change: {path}.")
            seen.add(path)
            protected, reason = is_protected_path(path)
            if protected:
                violations.append(f"{path}: {reason}")
            allowed, reason = allowed_for_task(path, task_type)
            if not allowed:
                violations.append(f"{path}: {reason}")
            if file_scope:
                scoped, scope_reason = allowed_by_prompt_scope(path, file_scope)
                if not scoped:
                    violations.append(f"{path}: {scope_reason}")
            if change.change_type == "delete":
                violations.append(f"{path}: delete operations are not enabled in Real Coding Agent v1.")
            if change.new_content is None and not change.edits:
                violations.append(f"{path}: new_content or exact edits are required.")
            elif change.new_content is not None and contains_secret_like_text(change.new_content):
                violations.append(f"{path}: proposed content appears to contain a secret or credential marker.")
            for edit in change.edits:
                if not edit.old_text:
                    violations.append(f"{path}: old_text is required for exact edits.")
                if contains_secret_like_text(edit.new_text):
                    violations.append(f"{path}: proposed edit appears to contain a secret or credential marker.")
            if change.edits and project_id:
                target = self.manager.resolve(project_id, path)
                before = target.read_text(encoding="utf-8") if target.exists() else ""
                for edit in change.edits:
                    count = before.count(edit.old_text)
                    if count == 0:
                        violations.append(f"{path}: old_text was not found exactly once for exact edit.")
                    elif count > 1:
                        violations.append(f"{path}: old_text is ambiguous for exact edit; found {count} matches.")
            if path.endswith(("requirements.txt", "package.json", "pyproject.toml")):
                warnings.append(f"{path}: dependency/config change requires human review before installs.")
        return PatchValidationResult(accepted=not violations, violations=violations, warnings=warnings)

    def apply(
        self,
        *,
        project_id: str,
        run_id: str,
        patch: ProposedPatch,
        dry_run: bool,
        agent_name: str = "Real Coding Agent",
    ) -> tuple[list[ProjectFileWriteResult], list[AppliedPatchFile]]:
        entries: list[ProjectFileWriteResult] = []
        applied: list[AppliedPatchFile] = []
        self.manager.ensure_project_workspace(project_id)
        for change in patch.files_to_change:
            path = change.path.replace("\\", "/")
            target = self.manager.resolve(project_id, path)
            before = target.read_text(encoding="utf-8") if target.exists() else ""
            after = _apply_exact_edits(before, change) if change.edits else (change.new_content or "")
            diff = unified_diff(before, after, path)
            operation = "updated" if target.exists() else "created"
            applied.append(
                AppliedPatchFile(
                    path=path,
                    operation=operation,
                    diff=diff,
                    summary=change.reason,
                    size_bytes=len(after.encode("utf-8")),
                )
            )
            if not dry_run:
                entries.append(
                    self.manager.write_project_file(
                        project_id=project_id,
                        relative_path=path,
                        content=after,
                        agent_name=agent_name,
                        run_id=run_id,
                        summary=change.reason,
                    )
                )
        return entries, applied


def unified_diff(before: str, after: str, path: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )[:12000]


def changed_paths_from_patch(patch: ProposedPatch | None) -> list[str]:
    if not patch:
        return []
    return [change.path.replace("\\", "/") for change in patch.files_to_change]


def _apply_exact_edits(content: str, change) -> str:
    updated = content
    for edit in change.edits:
        updated = updated.replace(edit.old_text, edit.new_text, 1)
    return updated
