from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.projects.schemas import ProjectWorkspaceSummary
from app.workspace.schemas import WorkspaceSummary


RunMode = Literal["mock", "live"]
RunStatus = Literal["queued", "planning", "selecting_models", "executing_workers", "reviewing", "running", "completed", "failed"]
EventStatus = Literal["pending", "running", "started", "completed", "failed", "blocked", "skipped"]


class RunCreate(BaseModel):
    command: str = Field(..., min_length=3, max_length=4000)
    mode: RunMode = "mock"
    project_id: str | None = Field(default=None, max_length=120)
    run_type: str = Field(default="business_launch_plan", max_length=120)
    allow_ceo_live: bool = False
    allow_file_writes: bool = False
    allow_safe_commands: bool = False
    max_cost_usd: float = Field(default=0.25, gt=0, le=5)


class AgentInfo(BaseModel):
    name: str
    role: str
    assigned_model: str
    status: str = "idle"
    latest_action: str = "Waiting for a run"
    completed_work: list[str] = Field(default_factory=list)


class RunEvent(BaseModel):
    timestamp: datetime
    run_id: str | None = None
    agent_name: str
    agent_role: str
    status: EventStatus
    action_summary: str
    input_summary: str
    output_summary: str
    model_used: str
    provider: str | None = None
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_tokens: int | None = None
    estimated_cost_usd: float
    estimated_cost: float | None = None
    artifact_id: str | None = None


class MemorySnippet(BaseModel):
    title: str
    content: str
    relevance_score: float


class MemorySummary(BaseModel):
    core_memory: str
    current_state: str
    retrieved_snippets: list[MemorySnippet]
    vector_store_path: str


class RunMetrics(BaseModel):
    total_estimated_tokens: int
    total_estimated_cost_usd: float
    agents_used: int
    tasks_completed: int
    run_duration_seconds: float
    memory_chunks_retrieved: int


class TaskNode(BaseModel):
    id: str
    label: str
    status: str


class TaskEdge(BaseModel):
    source: str
    target: str


class TaskGraph(BaseModel):
    nodes: list[TaskNode]
    edges: list[TaskEdge]


class FinalOutput(BaseModel):
    summary: str
    what_was_done: list[str]
    recommended_next_actions: list[str]
    generated_artifacts: list[str]


class Artifact(BaseModel):
    id: str
    run_id: str
    name: str
    type: str
    path: str
    created_at: str
    agent_name: str
    summary: str


class RunRecord(BaseModel):
    run_id: str
    command: str
    mode: RunMode
    project_id: str | None = None
    run_type: str = "business_launch_plan"
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None = None
    events: list[RunEvent]
    agents: list[AgentInfo]
    task_graph: TaskGraph
    metrics: RunMetrics
    memory: MemorySummary
    final_output: FinalOutput
    artifacts: list[Artifact] = Field(default_factory=list)
    workspace: WorkspaceSummary | None = None
    project_workspace: ProjectWorkspaceSummary | None = None
    models_used: list[str] = Field(default_factory=list)
    project_files_created: list[str] = Field(default_factory=list)
    project_files_updated: list[str] = Field(default_factory=list)
    commands_run: list[dict] = Field(default_factory=list)
    usage_summary: dict = Field(default_factory=dict)
    memory_updates: list[str] = Field(default_factory=list)
