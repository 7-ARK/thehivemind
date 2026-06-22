from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


TaskType = Literal[
    "website_copy_update",
    "website_ui_update",
    "backend_code_change",
    "frontend_code_change",
    "bug_fix",
    "documentation_update",
    "data_content_update",
    "mixed_code_task",
]


class ProjectFileMapEntry(BaseModel):
    path: str
    extension: str
    size_bytes: int
    last_modified: str | None = None
    purpose: str = ""
    editable: bool = True
    system_metadata: bool = False
    protected: bool = False
    binary: bool = False
    too_large: bool = False
    reason: str = ""


class RelevantFile(BaseModel):
    path: str
    reason: str
    content: str
    size_bytes: int


class AllowedUserFileScope(BaseModel):
    scope_type: str = "general"
    allowed_user_files: list[str] = Field(default_factory=list)
    blocked_user_files: list[str] = Field(default_factory=list)
    allowed_system_metadata: list[str] = Field(default_factory=lambda: ["project_state.md", "manifest.json"])
    reason: str = ""


class CodingContext(BaseModel):
    project_id: str
    run_id: str
    command: str
    task_type: TaskType
    allowed_user_file_scope: AllowedUserFileScope = Field(default_factory=AllowedUserFileScope)
    constraints: list[str] = Field(default_factory=list)
    file_map: list[ProjectFileMapEntry] = Field(default_factory=list)
    selected_files: list[RelevantFile] = Field(default_factory=list)
    memory_used: list[dict[str, Any]] = Field(default_factory=list)
    validation_options: list[list[str]] = Field(default_factory=list)


class CodingFileChange(BaseModel):
    path: str
    reason: str
    change_type: Literal["create", "modify", "delete"] = "modify"
    new_content: str | None = None
    edits: list["ExactTextEdit"] = Field(default_factory=list)


class ExactTextEdit(BaseModel):
    old_text: str
    new_text: str


class ProposedPatch(BaseModel):
    summary: str
    task_type: TaskType
    files_to_change: list[CodingFileChange] = Field(default_factory=list)
    files_read: list[str] = Field(default_factory=list)
    validation_commands: list[dict[str, Any]] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    memory_used: list[dict[str, Any]] = Field(default_factory=list)


class PatchValidationResult(BaseModel):
    accepted: bool
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AppliedPatchFile(BaseModel):
    path: str
    operation: str
    diff: str
    summary: str
    size_bytes: int = 0


class RepairLoopStatus(BaseModel):
    repair_enabled: bool = False
    max_attempts: int = 0
    attempts_made: int = 0
    reason_repair_started: str | None = None
    initial_validation_failed: bool = False
    initial_validation_command: list[str] = Field(default_factory=list)
    initial_validation_exit_code: int | None = None
    repair_patch_accepted: bool | None = None
    repair_patch_applied: bool = False
    repair_validation_passed: bool | None = None
    rollback_attempted: bool = False
    rollback_succeeded: bool | None = None
    rollback_failed_files: list[str] = Field(default_factory=list)
    final_result: str = "not_attempted"
    not_attempted_reason: str | None = None
    initial_patch_estimated_cost_usd: float = 0.0
    repair_patch_estimated_cost_usd: float = 0.0
    cost_cap_prevented_repair: bool = False
    artifacts: dict[str, dict[str, Any]] = Field(default_factory=dict)


class RealCodingAgentResult(BaseModel):
    enabled: bool
    used: bool
    actual_provider: str
    selected_model: str
    fallback_model: str | None = None
    fallback_model_used: bool = False
    live_call_made: bool = False
    mock_simulated: bool = False
    dry_run: bool = False
    hardcoded_fallback_used: bool = False
    patch_applied: bool = False
    no_change_reason: str | None = None
    parse_error: str | None = None
    parser_route: str | None = None
    parser_route_attempted: list[str] = Field(default_factory=list)
    provider_response_diagnostic: dict[str, Any] | None = None
    requested_max_output_tokens: int | None = None
    response_format_requested: str | None = None
    provider_response_finish_reason: str | None = None
    actual_output_tokens: int | None = None
    reasoning_tokens: int | None = None
    content_source: str | None = None
    repair_attempts: int = 0
    repair_loop: RepairLoopStatus = Field(default_factory=RepairLoopStatus)
    task_type: TaskType
    allowed_user_file_scope: AllowedUserFileScope = Field(default_factory=AllowedUserFileScope)
    files_inspected: list[str] = Field(default_factory=list)
    files_selected: list[str] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    rejected_files: list[str] = Field(default_factory=list)
    validation: PatchValidationResult
    proposed_patch: ProposedPatch | None = None
    applied_files: list[AppliedPatchFile] = Field(default_factory=list)
    validation_commands: list[dict[str, Any]] = Field(default_factory=list)
    memory_used: list[dict[str, Any]] = Field(default_factory=list)
    memory_exclusions: list[str] = Field(default_factory=list)
    search_context_used: bool = False
    notes: list[str] = Field(default_factory=list)
