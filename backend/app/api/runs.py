from fastapi import APIRouter, HTTPException

from app.core.models import RunCreate, RunRecord
from app.orchestration.run_manager import RunManager

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("", response_model=RunRecord)
def start_run(payload: RunCreate) -> RunRecord:
    return RunManager().start_run(command=payload.command, mode=payload.mode)


@router.get("/{run_id}", response_model=RunRecord)
def get_run(run_id: str) -> RunRecord:
    run = RunManager().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run

