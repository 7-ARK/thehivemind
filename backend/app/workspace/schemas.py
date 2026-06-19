from pydantic import BaseModel, Field


class FileManifestEntry(BaseModel):
    path: str
    agent_name: str
    timestamp: str
    size_bytes: int
    summary: str
    operation: str


class WorkspaceManifest(BaseModel):
    run_id: str
    files: list[FileManifestEntry] = Field(default_factory=list)


class CommandResult(BaseModel):
    command: list[str]
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    allowed: bool
    blocked_reason: str | None = None
    executable_command: list[str] = Field(default_factory=list)
    resolved_cwd: str | None = None
    error_type: str | None = None
    error_message: str | None = None


class WorkspaceSummary(BaseModel):
    root: str
    files_created: list[str] = Field(default_factory=list)
    files_edited: list[str] = Field(default_factory=list)
    commands_run: list[CommandResult] = Field(default_factory=list)
    command_success: bool | None = None
