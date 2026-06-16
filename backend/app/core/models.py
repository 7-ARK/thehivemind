from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


RunMode = Literal["mock", "live"]
RunStatus = Literal["queued", "running", "completed", "failed"]
EventStatus = Literal["started", "completed", "blocked"]


class RunCreate(BaseModel):
    command: str = Field(..., min_length=3, max_length=4000)
    mode: RunMode = "mock"


class AgentInfo(BaseModel):
    name: str
    role: str
    assigned_model: str
    status: str = "idle"
    latest_action: str = "Waiting for a run"
    completed_work: list[str] = Field(default_factory=list)


class RunEvent(BaseModel):
    timestamp: datetime
    agent_name: str
    agent_role: str
    status: EventStatus
    action_summary: str
    input_summary: str
    output_summary: str
    model_used: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_usd: float


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


class RunRecord(BaseModel):
    run_id: str
    command: str
    mode: RunMode
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None = None
    events: list[RunEvent]
    agents: list[AgentInfo]
    task_graph: TaskGraph
    metrics: RunMetrics
    memory: MemorySummary
    final_output: FinalOutput

