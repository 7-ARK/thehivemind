# TheHiveMind

TheHiveMind is a recruiter-friendly multi-agent AI operating system for planning, delegation, memory, and execution. A CEO agent receives a user command, creates a plan, routes worker tasks to appropriate models, retrieves relevant memory, logs each step, and assembles a final answer in a polished dashboard.

This repository is the initial MVP setup. It runs locally, defaults to mock mode, and avoids paid API calls while making the architecture easy to extend.

## Why It Exists

Most agent demos hide the actual operating system: who planned, which model was selected, what memory was retrieved, what each worker produced, and how much the run might cost. TheHiveMind makes that workflow legible. The UI is designed so a recruiter, technical lead, or founder can understand the system at a glance.

## Tech Stack

- Backend: Python, FastAPI, SQLite
- Frontend: Vite, React, TypeScript, Tailwind CSS
- Memory: local core memory, current state, and JSON text-chunk retrieval placeholder
- Providers: OpenAI, Google Gemini, OpenRouter, and mock provider interfaces
- Default execution: mock mode

## Current MVP Features

- `POST /api/runs` starts a controlled Run Engine v1 workflow.
- `GET /api/runs/{run_id}` fetches persisted run details from SQLite.
- `GET /api/runs/{run_id}/events` fetches timeline events.
- `GET /api/runs/{run_id}/artifacts` fetches artifact metadata.
- `GET /api/runs/{run_id}/artifacts/{artifact_id}` fetches one saved artifact.
- `GET /api/agents` returns the agent roster and assigned models.
- `GET /api/memory/summary` returns core memory, current state, and retrieved snippets.
- Dashboard renders command input, timeline, agents, task graph, metrics, memory, and final output.
- Cost estimates are generated from a simple pricing table.
- Provider adapters are present but live calls are disabled.

## Architecture

The current flow is:

`Command -> CEO Agent -> Model Selector -> Research/Content/Operations Workers -> QA Agent -> Final Output -> Artifacts`

The CEO agent owns the plan. The model selector chooses a sensible model tier for each task. Worker agents produce task-specific outputs. QA reviews the package before final assembly. Memory retrieval provides only relevant context instead of loading everything into every prompt.

## Agent Roles

- CEO Agent: receives the command, creates a plan, and delegates.
- Model Selector Agent: chooses the model for each work type.
- Research Agent: handles search-heavy and market/context tasks.
- Content Agent: drafts messaging, reports, and user-facing artifacts.
- Operations Agent: maps order flow, manual approvals, and launch operations.
- QA Agent: checks completeness, contradictions, and readiness.

## Memory And RAG

The MVP uses three memory layers:

- Core memory: durable identity and operating principles.
- Current state: latest truth about the active project.
- Vector memory placeholder: local JSON chunks with lexical scoring.

The interface is intentionally shaped like a future vector store. Later, `LocalVectorMemory` can be replaced with pgvector, Chroma, or another embedding-backed store.

## Model Routing

Planned default routing:

- CEO: GPT-5.5 Flex
- Model selector/search: Gemini 3.5 Flash
- Cheap non-search worker: GPT-5.4 nano
- Cheap search/multimodal worker: Gemini 3.1 Flash-Lite
- Coding later: Codex or Qwen Coder style specialized coding worker

These model names are configuration placeholders for the MVP and are not called in mock mode.

## Run Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend URL: `http://127.0.0.1:8000`

## Run Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite frontend is configured to use port `3001` with strict port binding.

Frontend URL: `http://localhost:3001`

## First Real Controlled Run

Run Engine v1 creates a sequential mock workflow, saved artifacts, memory updates, and usage logs without making live provider calls:

```bash
curl -X POST http://127.0.0.1:8000/api/runs ^
  -H "Content-Type: application/json" ^
  -d "{\"command\":\"Create a launch plan for a Greek yogurt business in Pakistan, excluding supplier sourcing and physical yogurt production.\",\"mode\":\"mock\",\"project_id\":\"greek-yogurt-test\",\"run_type\":\"business_launch_plan\",\"allow_ceo_live\":false,\"max_cost_usd\":0.25}"
```

Artifacts are saved under `backend/data/artifacts/{run_id}/`.

## Environment Variables

Copy `.env.example` to `.env` if needed. The repository includes a local placeholder `.env`, but `.env` is ignored by Git.

```bash
APP_ENV=development
MOCK_MODE=true
OPENAI_API_KEY=
OPENAI_TRACKING_ID=
GOOGLE_API_KEY=
OPENROUTER_API_KEY=
DATABASE_URL=sqlite:///./thehivemind.db
VECTOR_STORE_PATH=./data/vector_memory
ARTIFACT_STORE_PATH=./backend/data/artifacts
CURRENT_STATE_PATH=./backend/data/current_state.txt
```

## Screenshots

Screenshots will be added after the first visual pass:

- Dashboard empty state
- Completed mock run
- Agent workspace
- Memory panel

## Future Roadmap

- Stream run events over Server-Sent Events or WebSockets.
- Add live provider adapters with explicit user approval before paid calls.
- Replace lexical retrieval with embeddings and pgvector or Chroma.
- Add project workspaces, artifact storage, and approval checkpoints.
- Add auth, organization settings, and provider budget controls.
- Add evaluation traces for agent quality and routing decisions.
- Connect the frontend analytics dashboard to the usage tracking endpoints in `docs/usage_tracking.md`.

## What Is Still Mock

Mock runs produce deterministic structured artifacts. Provider classes exist, but OpenAI, Gemini, and OpenRouter live calls remain disabled unless `ALLOW_LIVE_CALLS=true`, the request uses `"mode":"live"`, limits pass, and CEO-live use is explicitly approved.
