# Project Workspace UI

The frontend now includes a Project Workspace tab in the Vite React dashboard.

It shows:

- `project_state.md`
- Project manifest
- File tree
- Safe selected file preview
- Run history
- File changes
- Command logs for the selected run
- Artifacts for the selected run

The UI calls:

- `GET /api/projects/{project_id}/state`
- `GET /api/projects/{project_id}/manifest`
- `GET /api/projects/{project_id}/files`
- `GET /api/projects/{project_id}/files/{path}`
- `GET /api/projects/{project_id}/runs`
- `GET /api/projects/{project_id}/changes`
- `GET /api/runs/{run_id}/commands`
- `GET /api/runs/{run_id}/artifacts`

The backend still enforces file safety. The frontend does not request `.env`, blocked paths, or raw secret material.

If the backend is offline, the panel shows a calm warning with the backend URL. If no files exist, it shows an empty state instead of fake data.
