from fastapi import APIRouter, HTTPException

from app.core.models import RunCreate, RunRecord
from app.artifacts.artifact_store import ArtifactStore
from app.artifacts.schemas import ArtifactContent
from app.core.models import Artifact, RunEvent
from app.orchestration.execution_engine import execute_run
from app.orchestration.run_manager import RunManager

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("", response_model=RunRecord)
async def start_run(payload: RunCreate) -> RunRecord:
    return await execute_run(
        command=payload.command,
        mode=payload.mode,
        project_id=payload.project_id,
        run_type=payload.run_type,
        allow_ceo_live=payload.allow_ceo_live,
        max_cost_usd=payload.max_cost_usd,
    )


@router.get("/{run_id}", response_model=RunRecord)
def get_run(run_id: str) -> RunRecord:
    run = RunManager().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/{run_id}/events", response_model=list[RunEvent])
def get_run_events(run_id: str) -> list[RunEvent]:
    run = get_run(run_id)
    return run.events


@router.get("/{run_id}/artifacts", response_model=list[Artifact])
def get_run_artifacts(run_id: str) -> list[Artifact]:
    if RunManager().get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return ArtifactStore().list_artifacts(run_id)


@router.get("/{run_id}/artifacts/{artifact_id}", response_model=ArtifactContent)
def get_run_artifact(run_id: str, artifact_id: str) -> ArtifactContent:
    if RunManager().get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return ArtifactStore().get_artifact(run_id, artifact_id)
