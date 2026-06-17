import json

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.core.models import RunCreate, RunRecord
from app.artifacts.artifact_store import ArtifactStore
from app.artifacts.schemas import ArtifactContent
from app.core.models import Artifact, RunEvent
from app.orchestration.execution_engine import execute_run
from app.orchestration.run_manager import RunManager
from app.workspace.schemas import CommandResult, WorkspaceManifest
from app.workspace.workspace_manager import WorkspaceManager

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("", response_model=RunRecord)
async def start_run(payload: RunCreate) -> RunRecord:
    return await execute_run(
        command=payload.command,
        mode=payload.mode,
        project_id=payload.project_id,
        run_type=payload.run_type,
        allow_ceo_live=payload.allow_ceo_live,
        allow_file_writes=payload.allow_file_writes,
        allow_safe_commands=payload.allow_safe_commands,
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


@router.get("/{run_id}/workspace/files")
def get_workspace_files(run_id: str) -> dict:
    if RunManager().get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    manifest = WorkspaceManager().read_manifest(run_id)
    return {"run_id": run_id, "files": [entry.model_dump() for entry in manifest.files]}


@router.get("/{run_id}/workspace/files/{file_path:path}")
def get_workspace_file(run_id: str, file_path: str) -> dict:
    if RunManager().get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    content = WorkspaceManager().read_workspace_file(run_id, file_path)
    return {"run_id": run_id, "path": file_path, "content": content}


@router.get("/{run_id}/workspace/manifest", response_model=WorkspaceManifest)
def get_workspace_manifest(run_id: str) -> WorkspaceManifest:
    if RunManager().get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return WorkspaceManager().read_manifest(run_id)


@router.get("/{run_id}/workspace/commands", response_model=list[CommandResult])
def get_workspace_commands(run_id: str) -> list[CommandResult]:
    return get_run_commands(run_id)


@router.get("/{run_id}/commands", response_model=list[CommandResult])
def get_run_commands(run_id: str) -> list[CommandResult]:
    run = RunManager().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.commands_run:
        return [CommandResult.model_validate(item) for item in run.commands_run]
    if run.workspace and run.workspace.commands_run:
        return run.workspace.commands_run
    run_commands_path = get_settings().run_path / run_id / "commands.json"
    if run_commands_path.exists():
        return [CommandResult.model_validate(item) for item in json.loads(run_commands_path.read_text(encoding="utf-8"))]
    return WorkspaceManager().read_commands(run_id)
