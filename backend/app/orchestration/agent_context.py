from pydantic import BaseModel, Field


class AgentExecutionContext(BaseModel):
    run_id: str
    project_id: str
    mode: str
    agent_name: str
    agent_role: str
    command: str
    task_objective: str
    relevant_memory: list[str] = Field(default_factory=list)
    relevant_project_files: list[dict] = Field(default_factory=list)
    input_artifacts: list[dict] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    model: str
    provider: str
    max_output_tokens: int
    max_cost_usd: float
