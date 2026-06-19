from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


MemoryScope = Literal["global", "project"]
MemoryType = Literal[
    "core_rule",
    "project_state",
    "run_summary",
    "research_brief",
    "research_source_summary",
    "model_selection",
    "agent_plan",
    "qa_warning",
    "safety_constraint",
    "user_preference",
    "file_change_summary",
    "command_result",
    "error_fix",
    "next_step",
]
SourceType = Literal[
    "manual",
    "artifact",
    "run",
    "project_state",
    "qa_review",
    "search_source",
    "model_selection",
    "command_log",
]


class MemoryItem(BaseModel):
    id: str
    project_id: str | None = None
    scope: MemoryScope = "project"
    memory_type: MemoryType
    title: str
    content: str
    summary: str = ""
    source_type: SourceType = "manual"
    source_path: str | None = None
    source_run_id: str | None = None
    source_artifact_id: str | None = None
    created_at: str
    updated_at: str
    tags: list[str] = Field(default_factory=list)
    importance: int = Field(default=3, ge=1, le=5)
    recency_score: float = 1.0
    trust_score: float = 0.8
    expires_at: str | None = None
    is_active: bool = True
    is_sensitive: bool = False
    should_inject_by_default: bool = True
    allowed_agents: list[str] = Field(default_factory=list)
    blocked_agents: list[str] = Field(default_factory=list)
    token_estimate: int = 0
    sparse_vector: dict[str, float] = Field(default_factory=dict)
    keywords: list[str] = Field(default_factory=list)
    normalized_text: str = ""
    hash: str = ""
    constraints: list[str] = Field(default_factory=list)
    models_used: list[str] = Field(default_factory=list)
    agents_used: list[str] = Field(default_factory=list)
    search_provider: str | None = None
    source_urls: list[str] = Field(default_factory=list)
    file_paths: list[str] = Field(default_factory=list)
    error_types: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemorySearchResult(BaseModel):
    item: MemoryItem
    score: float
    why_selected: list[str] = Field(default_factory=list)


class ContextPacket(BaseModel):
    agent_id: str
    project_id: str | None = None
    run_id: str | None = None
    run_type: str
    task: str
    current_command: str
    retrieved_memory_items: list[MemorySearchResult] = Field(default_factory=list)
    project_state_summary: str = ""
    active_constraints: list[str] = Field(default_factory=list)
    relevant_sources: list[str] = Field(default_factory=list)
    relevant_qa_warnings: list[str] = Field(default_factory=list)
    model_routing_notes: list[str] = Field(default_factory=list)
    token_budget: int = 1200
    omitted_memory_count: int = 0
    created_at: str


class MemoryRetrievalRequest(BaseModel):
    project_id: str | None = None
    query: str
    agent_id: str = "qa_agent"
    run_type: str = "research_only"
    task_type: str = "general"
    current_command: str = ""
    max_items: int = 5
    max_tokens: int = 1200
