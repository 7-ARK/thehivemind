from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentRegistryEntry(BaseModel):
    id: str
    display_name: str
    purpose: str
    when_to_use: list[str] = Field(default_factory=list)
    when_not_to_use: list[str] = Field(default_factory=list)
    allowed_run_types: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_file_scopes: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    blocked_actions: list[str] = Field(default_factory=list)
    default_models: list[str] = Field(default_factory=list)
    preferred_model_tags: list[str] = Field(default_factory=list)
    fallback_models: list[str] = Field(default_factory=list)
    requires_live: bool = False
    can_run_in_mock: bool = True
    can_use_search: bool = False
    can_write_files: bool = False
    can_run_safe_commands: bool = False
    requires_approval_for: list[str] = Field(default_factory=list)
    input_context_needed: list[str] = Field(default_factory=list)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    memory_needed: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    qa_checks: list[str] = Field(default_factory=list)
    status: str = "active"


class PlannedAgent(BaseModel):
    agent_id: str
    objective: str
    required_capabilities: list[str] = Field(default_factory=list)
    required_model_capabilities: list[str] = Field(default_factory=list)
    required_search_tool_capabilities: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    allowed_files: list[str] = Field(default_factory=list)
    blocked_actions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    needs_model_selection: bool = True
    selected_model: dict[str, Any] | None = None
    selected_search_provider: dict[str, Any] | None = None


class SkippedAgent(BaseModel):
    agent_id: str
    reason: str


class AgentPlanRequest(BaseModel):
    command: str
    run_type: str = "business_launch_plan"
    project_id: str | None = None
    mode: str = "mock"
    allow_file_writes: bool = False
    allow_safe_commands: bool = False
    allow_search: bool = False
    max_cost_usd: float = 0.25


class AgentPlanResult(BaseModel):
    run_goal: str
    selected_workflow: str
    selected_agents: list[PlannedAgent]
    skipped_agents: list[SkippedAgent]
    safety_constraints: list[str] = Field(default_factory=list)
    blocked_actions: list[str] = Field(default_factory=list)
    memory_requirements: list[str] = Field(default_factory=list)
    approval_required: bool = False
    search_needed: bool = False
    search_unavailable: bool = False
    selected_search_provider: dict[str, Any] | None = None
    combined_search_used: bool = False
    proposed_agent_requires_review: bool = False
    notes: list[str] = Field(default_factory=list)
