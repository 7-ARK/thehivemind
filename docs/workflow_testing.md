# Workflow Testing Backend Mode

Use **no-reload mode** before mock or live agent workflow testing.

Generated project files are stored under `backend/data/projects/`. If Uvicorn is started with a broad `--reload` watcher, file writes from an agent run can restart the backend during validation commands.

## Backend Code Development

Use reload when editing backend code:

```powershell
cd C:\Users\Ahmed\thehivemind\backend
.\scripts\run_api_dev.ps1
```

This script scopes reload to `backend/app`.

## Agent Workflow Testing

Use no-reload mode before workflow testing:

```powershell
cd C:\Users\Ahmed\thehivemind\backend
.\scripts\run_api_workflow.ps1
```

Equivalent command:

```powershell
uvicorn app.main:app --port 8000
```

This avoids backend restarts while agents write project files and safe validation commands run.
