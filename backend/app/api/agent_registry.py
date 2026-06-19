from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.agent_registry.planner_service import AgentPlannerService
from app.agent_registry.registry_loader import AgentRegistryLoader
from app.agent_registry.schemas import AgentPlanRequest, AgentPlanResult
from app.core.config import get_settings

router = APIRouter(prefix="/api/agent-registry", tags=["agent-registry"])


@router.get("/agents")
def list_agents() -> dict:
    loader = AgentRegistryLoader()
    return {"agents": [agent.model_dump() for agent in loader.agents()]}


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str) -> dict:
    agent = AgentRegistryLoader().get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return agent.model_dump()


@router.post("/plan", response_model=AgentPlanResult)
def plan_agents(payload: AgentPlanRequest) -> AgentPlanResult:
    settings = get_settings()
    if "allow_search" not in payload.model_fields_set and settings.allow_web_search:
        payload = payload.model_copy(update={"allow_search": True})
    return AgentPlannerService().plan(payload)
