# TheHiveMind

TheHiveMind is a recruiter-friendly multi-agent AI operating system for planning, delegation, memory, and execution. A CEO agent receives a user command, creates a plan, routes worker tasks to appropriate models, retrieves relevant memory, logs each step, and assembles a final answer in a polished dashboard.

This repository is the initial MVP setup. It runs locally, defaults to mock mode, and avoids paid API calls while making the architecture easy to extend.

## Why It Exists

Most agent demos hide the actual operating system: who planned, which model was selected, what memory was retrieved, what each worker produced, and how much the run might cost. TheHiveMind makes that workflow legible. The UI is designed so a recruiter, technical lead, or founder can understand the system at a glance.

## Tech Stack

- Backend: Python, FastAPI, SQLite
- Frontend: Next.js, TypeScript, Tailwind CSS
- Memory: local core memory, current state, and JSON text-chunk retrieval placeholder
- Providers: OpenAI, Google Gemini, OpenRouter, and mock provider interfaces
- Default execution: mock mode

## Current MVP Features

- `POST /api/runs` starts a mock multi-agent run.
- `GET /api/runs/{run_id}` fetches persisted run details from SQLite.
- `GET /api/agents` returns the agent roster and assigned models.
- `GET /api/memory/summary` returns core memory, current state, and retrieved snippets.
- Dashboard renders command input, timeline, agents, task graph, metrics, memory, and final output.
- Cost estimates are generated from a simple pricing table.
- Provider adapters are present but live calls are disabled.

## Architecture

The current flow is:

`Command -> CEO Agent -> Model Selector -> Research/Coding/Content Workers -> QA Agent -> Final Output`

The CEO agent owns the plan. The model selector chooses a sensible model tier for each task. Worker agents produce task-specific outputs. QA reviews the package before final assembly. Memory retrieval provides only relevant context instead of loading everything into every prompt.

## Agent Roles

- CEO Agent: receives the command, creates a plan, and delegates.
- Model Selector Agent: chooses the model for each work type.
- Research Agent: handles search-heavy and market/context tasks.
- Coding Agent: maps the plan into technical systems and implementation tasks.
- Content Agent: drafts messaging, reports, and user-facing artifacts.
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

Frontend URL: `http://localhost:3000`

## Environment Variables

Copy `.env.example` to `.env` if needed. The repository includes a local placeholder `.env`, but `.env` is ignored by Git.

```bash
APP_ENV=development
MOCK_MODE=true
OPENAI_API_KEY=
GOOGLE_API_KEY=
OPENROUTER_API_KEY=
DATABASE_URL=sqlite:///./thehivemind.db
VECTOR_STORE_PATH=./data/vector_memory
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

## What Is Still Mock

All agent outputs are deterministic mock responses. Provider classes exist, but OpenAI, Gemini, and OpenRouter calls are intentionally disabled until API key handling, budgets, and live-call controls are implemented.

