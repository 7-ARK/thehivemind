# TheHiveMind Backend

FastAPI service for the TheHiveMind MVP. It exposes mock multi-agent run orchestration, local SQLite run logs, and a replaceable local memory abstraction.

## Run Locally

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

## Key Endpoints

- `GET /health`
- `POST /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/events`
- `GET /api/runs/{run_id}/artifacts`
- `GET /api/runs/{run_id}/artifacts/{artifact_id}`
- `GET /api/projects`
- `GET /api/projects/{project_id}`
- `GET /api/projects/{project_id}/state`
- `GET /api/projects/{project_id}/manifest`
- `GET /api/projects/{project_id}/files`
- `GET /api/projects/{project_id}/runs`
- `GET /api/projects/{project_id}/changes`
- `GET /api/agents`
- `GET /api/memory/summary`
- `GET /api/providers/status`
- `POST /api/providers/test`
- `GET /api/usage/summary`

Mock mode is enabled by default. Provider adapters exist, but live paid calls are intentionally disabled in this MVP.

## First Controlled Run

Run Engine v1 creates a sequential planning workflow, saves artifacts, updates memory, and logs usage:

```bash
curl -X POST http://127.0.0.1:8000/api/runs ^
  -H "Content-Type: application/json" ^
  -d "{\"command\":\"Create a launch plan for a Greek yogurt business in Pakistan, excluding supplier sourcing and physical yogurt production.\",\"mode\":\"mock\",\"project_id\":\"greek-yogurt-test\",\"run_type\":\"business_launch_plan\",\"allow_ceo_live\":false,\"max_cost_usd\":0.25}"
```

Artifacts are written to `backend/data/artifacts/{run_id}/`.

## Persistent Project Workspace

Prototype builds create or update files inside `backend/data/projects/{project_id}/` and save per-run logs under `backend/data/runs/{run_id}/`:

```bash
curl -X POST http://127.0.0.1:8000/api/runs ^
  -H "Content-Type: application/json" ^
  -d "{\"command\":\"Create a simple Greek yogurt order website prototype with files.\",\"mode\":\"mock\",\"project_id\":\"greek-yogurt-test\",\"run_type\":\"prototype_build\",\"allow_file_writes\":true,\"allow_safe_commands\":true,\"allow_ceo_live\":false,\"max_cost_usd\":0.25}"
```

Continue the same project in a later run:

```bash
curl -X POST http://127.0.0.1:8000/api/runs ^
  -H "Content-Type: application/json" ^
  -d "{\"command\":\"Continue the Greek yogurt website and add a simple order status page.\",\"mode\":\"mock\",\"project_id\":\"greek-yogurt-test\",\"run_type\":\"prototype_build\",\"allow_file_writes\":true,\"allow_safe_commands\":true,\"allow_ceo_live\":false,\"max_cost_usd\":0.25}"
```

The project workspace blocks `.env`, path traversal, dangerous commands, package installs, Git pushes/resets, and writes outside the approved project directory.

## Safe Provider Testing

Live provider calls are blocked unless all of these are true:

- The request body uses `"mode": "live"`.
- `.env` has `ALLOW_LIVE_CALLS=true`.
- The call goes through `POST /api/providers/test` or the guarded provider router.
- The target provider has an API key configured.
- The input, output, and cost estimates are under the configured limits.

Mock provider tests work without API keys:

```bash
curl -X POST http://127.0.0.1:8000/api/providers/test ^
  -H "Content-Type: application/json" ^
  -d "{\"provider\":\"openai\",\"model\":\"gpt-5.4-nano\",\"mode\":\"mock\",\"prompt\":\"Reply with one short sentence saying TheHiveMind provider test worked.\",\"max_output_tokens\":80}"
```

To safely test OpenAI with the cheap worker model:

1. Set `ALLOW_LIVE_CALLS=true`.
2. Set `OPENAI_API_KEY`.
3. Keep `MAX_OUTPUT_TOKENS_PER_CALL` and `MAX_COST_PER_CALL_USD` low.
4. Use `model: "gpt-5.4-nano"` and a short prompt through `POST /api/providers/test`.

To safely test Gemini Flash-Lite:

1. Set `ALLOW_LIVE_CALLS=true`.
2. Set `GOOGLE_API_KEY`.
3. Use `provider: "gemini"` and `model: "gemini-3.1-flash-lite"`.

OpenRouter can be tested similarly with `OPENROUTER_API_KEY` and `model: "qwen/qwen3-coder"`.

## Usage Tracking

Every provider test call writes a SQLite usage row with provider, model, mode, token counts, estimated cost, latency, success/failure, request type, and sanitized metadata. Check totals with:

```bash
curl http://127.0.0.1:8000/api/usage/summary
```

Detailed analytics endpoints and CSV export are documented in `../docs/usage_tracking.md`.

## Search And Grounding

Web search, Gemini grounding, and OpenRouter search plugins are disabled by default:

- `ENABLE_OPENAI_WEB_SEARCH=false`
- `ENABLE_GEMINI_GROUNDING=false`
- `ENABLE_OPENROUTER_SEARCH=false`

The provider adapters do not send search tool/plugin configuration in this step.
