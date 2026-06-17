from pathlib import Path

from app.projects.project_manifest import utc_now


def default_project_state(project_id: str) -> str:
    return f"""# Project State

## Project
{project_id}

## Current Goal
Build the project through controlled, sandboxed runs.

## Current Status
Workspace created. No project files have been generated yet.

## What Has Been Built
- Nothing yet.

## Important Decisions
- Keep file writes inside the persistent project workspace.
- Keep run logs separate from project files.

## Open Tasks
- Run the first project build.

## Next Recommended Steps
- Create the first prototype or planning artifacts.

## Last Updated Run ID
none
"""


def ensure_project_state(path: Path, project_id: str) -> None:
    if not path.exists():
        path.write_text(default_project_state(project_id), encoding="utf-8")


def update_project_state(
    path: Path,
    *,
    project_id: str,
    run_id: str,
    command: str,
    files_created: list[str],
    files_edited: list[str],
    command_success: bool | None,
    next_steps: list[str],
) -> str:
    status = "Validated successfully" if command_success else "Generated with validation notes"
    created = "\n".join(f"- {item}" for item in files_created) or "- None"
    edited = "\n".join(f"- {item}" for item in files_edited) or "- None"
    steps = "\n".join(f"- {item}" for item in next_steps) or "- Review the project files."
    content = f"""# Project State

## Project
{project_id}

## Current Goal
{command}

## Current Status
{status}

## What Has Been Built
Created files:
{created}

Updated files:
{edited}

## Important Decisions
- Project files live in `backend/data/projects/{project_id}/`.
- Run-specific logs live in `backend/data/runs/{run_id}/`.
- External actions, deployments, package installs, and secret files remain blocked.

## Open Tasks
- Review generated project files before manual use.
- Confirm product copy, pricing, delivery, and operational claims with a human.

## Next Recommended Steps
{steps}

## Last Updated Run ID
{run_id}

## Last Updated At
{utc_now()}
"""
    path.write_text(content, encoding="utf-8")
    return content
