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
- `GET /api/agents`
- `GET /api/memory/summary`

Mock mode is enabled by default. Provider adapters exist, but live paid calls are intentionally disabled in this MVP.
