from fastapi import APIRouter, HTTPException

from app.projects.project_workspace import ProjectWorkspaceManager
from app.projects.schemas import ProjectFile, ProjectManifest, ProjectWorkspace

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
def list_projects() -> dict:
    return {"projects": ProjectWorkspaceManager().list_projects()}


@router.get("/{project_id}", response_model=ProjectWorkspace)
def get_project(project_id: str) -> ProjectWorkspace:
    return ProjectWorkspaceManager().ensure_project_workspace(project_id)


@router.get("/{project_id}/state")
def get_project_state(project_id: str) -> dict:
    manager = ProjectWorkspaceManager()
    manager.ensure_project_workspace(project_id)
    return {"project_id": project_id, "path": "project_state.md", "content": manager.read_project_file(project_id, "project_state.md")}


@router.get("/{project_id}/manifest", response_model=ProjectManifest)
def get_project_manifest(project_id: str) -> ProjectManifest:
    return ProjectWorkspaceManager().get_project_manifest(project_id)


@router.get("/{project_id}/files", response_model=list[ProjectFile])
def get_project_files(project_id: str) -> list[ProjectFile]:
    return ProjectWorkspaceManager().list_project_files(project_id)


@router.get("/{project_id}/runs")
def get_project_runs(project_id: str) -> dict:
    manifest = ProjectWorkspaceManager().get_project_manifest(project_id)
    return {"project_id": project_id, "runs": [item.model_dump() for item in manifest.runs]}


@router.get("/{project_id}/changes")
def get_project_changes(project_id: str) -> dict:
    return {"project_id": project_id, "changes": ProjectWorkspaceManager().project_changes(project_id)}


@router.get("/{project_id}/files/{file_path:path}")
def get_project_file(project_id: str, file_path: str) -> dict:
    try:
        content = ProjectWorkspaceManager().read_project_file(project_id, file_path)
    except HTTPException:
        raise
    return {"project_id": project_id, "path": file_path, "content": content}
