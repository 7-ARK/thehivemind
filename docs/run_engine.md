# Run Engine v1

Run Engine v1 is the first controlled workflow path for TheHiveMind. It turns one command into a sequential multi-agent run, saves stage artifacts, updates local memory, and logs usage by provider, model, agent, request type, token estimate, cost estimate, latency, and status.

## Flow

```text
Command
-> CEO Planning
-> Model Selection
-> Worker Task Execution
-> QA Review
-> Final Report
-> Save Artifacts
-> Update Memory
-> Log Usage
```

Execution is sequential in v1 for reliability and observability. Parallel workers, streaming, and autonomous actions are intentionally left for later.

## What It Does

- Creates a run ID and saved run record.
- Retrieves core memory, current state, and local vector-memory snippets.
- Produces CEO, model selector, research, content, operations, QA, and final report outputs.
- Saves artifacts under `backend/data/artifacts/{run_id}/`.
- Logs usage rows for every step.
- Updates current state and stores a compact run summary in vector memory.

## What It Does Not Do Yet

- It does not send emails.
- It does not post to social media.
- It does not deploy code.
- It does not source suppliers or handle physical production.
- It does not enable web search or grounding.
- It does not call live providers unless live mode is explicitly enabled and all safety checks pass.

## Main Endpoint

```http
POST /api/runs
```

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/runs ^
  -H "Content-Type: application/json" ^
  -d "{\"command\":\"Create a launch plan for a Greek yogurt business in Pakistan, excluding supplier sourcing and physical yogurt production.\",\"mode\":\"mock\",\"project_id\":\"greek-yogurt-test\",\"run_type\":\"business_launch_plan\",\"allow_ceo_live\":false,\"max_cost_usd\":0.25}"
```

## Run Statuses

Run Engine v1 currently persists the final completed record after the synchronous run finishes. The schema supports:

- `queued`
- `planning`
- `selecting_models`
- `executing_workers`
- `reviewing`
- `completed`
- `failed`

Polling is the supported v1 client behavior. SSE streaming is planned next.
