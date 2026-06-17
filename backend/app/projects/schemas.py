from pydantic import BaseModel, Field


class ProjectFile(BaseModel):
    path: str
    file_type: str
    size_bytes: int
    summary: str
    updated_at: str


class ProjectManifestFile(BaseModel):
    path: str
    created_at: str
    updated_at: str
    created_by: str
    last_modified_by: str
    last_run_id: str
    file_type: str
    size_bytes: int
    summary: str


class ProjectRunEntry(BaseModel):
    run_id: str
    summary: str
    created_at: str


class ProjectManifest(BaseModel):
    project_id: str
    created_at: str
    updated_at: str
    files: list[ProjectManifestFile] = Field(default_factory=list)
    runs: list[ProjectRunEntry] = Field(default_factory=list)


class ProjectWorkspace(BaseModel):
    project_id: str
    root: str
    state_path: str
    manifest_path: str


class ProjectFileWriteResult(BaseModel):
    project_id: str
    path: str
    operation: str
    agent_name: str
    run_id: str
    size_bytes: int
    before_summary: str | None = None
    after_summary: str
    timestamp: str


class FileChange(BaseModel):
    project_id: str
    run_id: str
    path: str
    operation: str
    agent_name: str
    before_summary: str | None = None
    after_summary: str
    timestamp: str


class ProjectWorkspaceSummary(BaseModel):
    project_id: str
    root: str
    files_created: list[str] = Field(default_factory=list)
    files_edited: list[str] = Field(default_factory=list)
    commands_run: list[dict] = Field(default_factory=list)
    command_success: bool | None = None
    state_path: str = "project_state.md"
    manifest_path: str = "manifest.json"
