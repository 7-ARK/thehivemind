import json

from fastapi import APIRouter, HTTPException

from app.approvals.approval_engine import ApprovalEngine
from app.approvals.schemas import ApprovalRequiredResponse
from app.core.config import get_settings
from app.core.models import RunCreate, RunRecord
from app.artifacts.artifact_store import ArtifactStore
from app.artifacts.schemas import ArtifactContent
from app.core.models import Artifact, RunEvent
from app.coding.coding_policy import is_focused_website_update
from app.orchestration.execution_engine import execute_run
from app.orchestration.run_manager import RunManager
from app.projects.project_diff import read_file_changes
from app.projects.project_workspace import ProjectWorkspaceManager
from app.projects.schemas import ProjectWorkspaceSummary
from app.workspace.schemas import CommandResult, WorkspaceManifest
from app.workspace.schemas import WorkspaceSummary
from app.workspace.workspace_manager import WorkspaceManager
from app.usage_sync.provider_sync_service import ProviderSyncService

router = APIRouter(prefix="/api/runs", tags=["runs"])


RunStartResponse = RunRecord | ApprovalRequiredResponse


@router.post("", response_model=RunStartResponse)
async def start_run(payload: RunCreate) -> RunStartResponse:
    payload = _apply_prompt_safety_overrides(payload)
    approval_response = ApprovalEngine().require_or_create(payload)
    if approval_response is not None:
        return approval_response
    record = await execute_run(
        command=payload.command,
        mode=payload.mode,
        project_id=payload.project_id,
        run_type=payload.run_type,
        allow_ceo_live=payload.allow_ceo_live,
        allow_file_writes=payload.allow_file_writes,
        allow_safe_commands=payload.allow_safe_commands,
        allow_web_search=payload.allow_web_search,
        use_memory=payload.use_memory,
        use_real_coding_agent=payload.use_real_coding_agent,
        allow_live_coding_model_call=payload.allow_live_coding_model_call,
        real_coding_dry_run=payload.real_coding_dry_run,
        real_coding_model=payload.real_coding_model,
        real_coding_max_files=payload.real_coding_max_files,
        real_coding_max_repair_attempts=payload.real_coding_max_repair_attempts,
        max_cost_usd=payload.max_cost_usd,
    )
    if record.mode == "live":
        sync_result = await ProviderSyncService().sync_after_live_run()
        record.usage_summary = {**record.usage_summary, "official_usage_sync": sync_result}
    return record


def _apply_prompt_safety_overrides(payload: RunCreate) -> RunCreate:
    command = payload.command.lower()
    updates = {}
    if payload.run_type in {"prototype_build", "continuation", "business_launch_plan"} and is_focused_website_update(payload.command):
        updates["run_type"] = "website_update"
        updates["allow_file_writes"] = True
        updates["use_real_coding_agent"] = True
        updates["allow_ceo_live"] = False
    if any(phrase in command for phrase in ("do not create files", "don't create files", "no file writes", "do not write files")):
        updates["allow_file_writes"] = False
    if any(phrase in command for phrase in ("do not update files", "don't update files", "research only", "only research")):
        updates["allow_file_writes"] = False
        updates["run_type"] = "research_only"
        updates["allow_safe_commands"] = False
    if any(phrase in command for phrase in ("do not run commands", "don't run commands", "no commands", "do not execute commands")):
        updates["allow_safe_commands"] = False
    if any(phrase in command for phrase in ("do not search", "don't search", "no web search", "do not browse", "do not run live web search")):
        updates["allow_web_search"] = False
    return payload.model_copy(update=updates) if updates else payload


@router.get("/{run_id}", response_model=RunRecord)
def get_run(run_id: str) -> RunRecord:
    run = RunManager().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _hydrate_run_summary(run)


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


@router.get("/{run_id}/model-selection")
def get_run_model_selection(run_id: str) -> dict:
    run = RunManager().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.model_selection:
        return {"run_id": run_id, "model_selection": run.model_selection}
    artifact = _artifact_json_by_name(run_id, "model_selection.json")
    return {"run_id": run_id, "model_selection": artifact or {}}


@router.get("/{run_id}/agent-plan")
def get_run_agent_plan(run_id: str) -> dict:
    run = RunManager().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.agent_plan:
        return {"run_id": run_id, "agent_plan": run.agent_plan}
    artifact = _artifact_json_by_name(run_id, "agent_plan.json")
    return {"run_id": run_id, "agent_plan": artifact or {}}


def _hydrate_run_summary(run: RunRecord) -> RunRecord:
    """Repair summary fields from run logs for older/stale stored payloads."""
    settings = get_settings()
    artifacts = run.artifacts or ArtifactStore(settings).list_artifacts(run.run_id)
    changes = read_file_changes(run.run_id, settings)
    commands = _load_commands_from_record_or_logs(run)

    created = [change.path for change in changes if change.operation == "created"]
    updated = [change.path for change in changes if change.operation == "updated"]
    if not created:
        created = _unique_paths(run.project_files_created or (run.workspace.files_created if run.workspace else []))
    if not updated:
        updated = _unique_paths(run.project_files_updated or (run.workspace.files_edited if run.workspace else []))
    if not created and not updated:
        artifact_paths = [artifact.name for artifact in artifacts if artifact.type == "project_file"]
        updated = _unique_paths(artifact_paths)

    commands_payload = [command.model_dump() for command in commands]
    root = ProjectWorkspaceManager(settings).public_root(run.project_id) if run.project_id else f"backend/data/runs/{run.run_id}"
    workspace = run.workspace or WorkspaceSummary(root=root)
    workspace.files_created = workspace.files_created or created
    workspace.files_edited = workspace.files_edited or updated
    workspace.commands_run = workspace.commands_run or commands
    workspace.command_success = workspace.command_success if workspace.command_success is not None else _commands_success(commands)

    project_workspace = run.project_workspace
    if run.project_id:
        project_workspace = project_workspace or ProjectWorkspaceSummary(project_id=run.project_id, root=root)
        project_workspace.files_created = project_workspace.files_created or created
        project_workspace.files_edited = project_workspace.files_edited or updated
        project_workspace.commands_run = project_workspace.commands_run or commands_payload
        project_workspace.command_success = project_workspace.command_success if project_workspace.command_success is not None else _commands_success(commands)

    usage_summary = run.usage_summary or {
        "estimated_cost_usd": run.metrics.total_estimated_cost_usd,
        "estimated_tokens": run.metrics.total_estimated_tokens,
        "agents_used": run.metrics.agents_used,
        "models_used": sorted({event.model_used for event in run.events}),
    }

    return run.model_copy(
        update={
            "artifacts": artifacts,
            "workspace": workspace,
            "project_workspace": project_workspace,
            "models_used": run.models_used or sorted({event.model_used for event in run.events}),
            "project_files_created": run.project_files_created or created,
            "project_files_updated": run.project_files_updated or updated,
            "commands_run": run.commands_run or commands_payload,
            "usage_summary": usage_summary,
        }
    )


def _load_commands_from_record_or_logs(run: RunRecord) -> list[CommandResult]:
    if run.commands_run:
        return [CommandResult.model_validate(item) for item in run.commands_run]
    if run.workspace and run.workspace.commands_run:
        return run.workspace.commands_run
    run_commands_path = get_settings().run_path / run.run_id / "commands.json"
    if run_commands_path.exists():
        return [CommandResult.model_validate(item) for item in json.loads(run_commands_path.read_text(encoding="utf-8"))]
    try:
        return WorkspaceManager().read_commands(run.run_id)
    except Exception:
        return []


def _commands_success(commands: list[CommandResult]) -> bool | None:
    if not commands:
        return None
    return all(command.allowed and command.exit_code == 0 for command in commands)


def _unique_paths(paths: list[str]) -> list[str]:
    seen = set()
    result = []
    for path in paths:
        if path and path not in seen:
            seen.add(path)
            result.append(path)
    return result


def _artifact_json_by_name(run_id: str, name: str) -> dict | None:
    store = ArtifactStore()
    for artifact in store.list_artifacts(run_id):
        if artifact.name != name:
            continue
        try:
            return json.loads(store.get_artifact(run_id, artifact.id).content)
        except Exception:
            return None
    return None
