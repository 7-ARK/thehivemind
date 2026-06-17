# Project Workspace

Persistent Project Workspace v1 gives each project a durable local folder:

```text
backend/data/projects/{project_id}/
```

This folder is the current working truth for the project. Agents can create and edit approved file types inside it, but they cannot touch `.env`, secret folders, dependency folders, hidden repo files, or paths that escape the project root.

For the Greek yogurt prototype, files are written to:

```text
backend/data/projects/greek-yogurt-test/
├── project_state.md
├── manifest.json
├── website/
│   ├── README.md
│   ├── app.py
│   ├── requirements.txt
│   ├── data/
│   │   └── sample_orders.json
│   └── templates/
│       └── index.html
└── logs/
    └── project_history.json
```

The manifest records every tracked project file, who created it, who last modified it, which run touched it, size, file type, and a short summary.

The `project_state.md` file is the latest truth: current goal, current status, what has been built, decisions, open tasks, next steps, and the last updated run id. It is intentionally summary-only so it does not become a token sink.

Safety rules are shared with the sandbox layer:

- Allowed extensions: `.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.json`, `.md`, `.txt`, `.html`, `.css`, `.yml`, `.yaml`, `.toml`
- Blocked paths include `.env`, `*.env`, `.git`, `node_modules`, `.venv`, `__pycache__`, `dist`, `build`, `.next`, and `secrets`
- Path traversal such as `../../` is rejected
- Dangerous commands, package installs, deployments, Git pushes/resets, email, social posting, and spending money remain outside v1
