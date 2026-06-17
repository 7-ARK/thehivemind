from pydantic import BaseModel, Field


class TaskPacket(BaseModel):
    run_id: str
    project_id: str | None = None
    task_id: str
    agent_name: str
    agent_role: str
    objective: str
    relevant_memory: list[str] = Field(default_factory=list)
    relevant_project_files: list[dict] = Field(default_factory=list)
    input_artifacts: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
