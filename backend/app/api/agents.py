from fastapi import APIRouter

from app.core.models import AgentInfo
from app.orchestration.run_manager import RunManager

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("", response_model=list[AgentInfo])
def get_agents() -> list[AgentInfo]:
    return RunManager().list_agents()

