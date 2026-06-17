from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api import agents, health, memory, projects, providers, runs, usage

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
app.include_router(runs.router)
app.include_router(projects.router)
app.include_router(agents.router)
app.include_router(memory.router)
app.include_router(providers.router)
app.include_router(usage.router)


@app.get("/", tags=["health"])
def api_index() -> dict[str, object]:
    return {
        "name": "TheHiveMind API",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "runs": "/api/runs",
            "projects": "/api/projects",
            "agents": "/api/agents",
            "memory": "/api/memory/summary",
            "providers": "/api/providers/status",
            "usage": "/api/usage/summary",
        },
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)
