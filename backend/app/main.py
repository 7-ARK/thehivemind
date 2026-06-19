from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api import agent_registry, agents, approvals, health, memory, model_registry, official_usage, projects, providers, runs, search_tools, usage

app = FastAPI(
    title="TheHiveMind API",
    description="Recruiter-friendly multi-agent orchestration MVP.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001", "http://127.0.0.1:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(approvals.router)
app.include_router(runs.router)
app.include_router(projects.router)
app.include_router(agents.router)
app.include_router(agent_registry.router)
app.include_router(model_registry.router)
app.include_router(search_tools.router)
app.include_router(memory.router)
app.include_router(providers.router)
app.include_router(usage.router)
app.include_router(official_usage.router)


@app.get("/", tags=["health"])
def api_index() -> dict[str, object]:
    return {
        "name": "TheHiveMind API",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "runs": "/api/runs",
            "approvals": "/api/approvals",
            "projects": "/api/projects",
            "agents": "/api/agents",
            "agent_registry": "/api/agent-registry/agents",
            "model_registry": "/api/model-registry/summary",
            "search_tools": "/api/search-tools/status",
            "memory": "/api/memory/status",
            "providers": "/api/providers/status",
            "usage": "/api/usage/summary",
            "official_usage": "/api/official-usage/status",
        },
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)
