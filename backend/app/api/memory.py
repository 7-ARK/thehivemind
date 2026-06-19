from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.models import MemorySummary
from app.memory.context_packet import build_context_packet
from app.memory.memory_ingestor import MemoryIngestor
from app.memory.memory_retriever import MemoryRetriever
from app.memory.memory_store import MemoryStore
from app.memory.retrieval import retrieve_memory
from app.memory.schemas import MemoryRetrievalRequest
from app.orchestration.run_manager import RunManager

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/summary", response_model=MemorySummary)
def get_memory_summary() -> MemorySummary:
    return retrieve_memory("TheHiveMind MVP orchestration")


@router.get("/status")
def memory_status() -> dict:
    return MemoryStore().status()


@router.get("/projects/{project_id}/items")
def project_memory_items(project_id: str, memory_type: str | None = None, limit: int = 50) -> dict:
    items = MemoryStore().items(project_id=project_id, memory_type=memory_type, include_global=False)
    return {"project_id": project_id, "items": [item.model_dump() for item in items[-limit:]][::-1]}


@router.get("/projects/{project_id}/search")
def project_memory_search(project_id: str, q: str = Query(..., min_length=1), agent_id: str = "qa_agent", run_type: str = "research_only", limit: int = 5) -> dict:
    request = MemoryRetrievalRequest(project_id=project_id, query=q, current_command=q, agent_id=agent_id, run_type=run_type, max_items=limit)
    results = MemoryRetriever().retrieve(request)
    return {"project_id": project_id, "query": q, "results": [result.model_dump() for result in results]}


@router.post("/projects/{project_id}/rebuild")
def rebuild_project_memory(project_id: str) -> dict:
    return MemoryStore().rebuild_index(project_id)


@router.post("/runs/{run_id}/ingest")
def ingest_run_memory(run_id: str) -> dict:
    result = MemoryIngestor().ingest_run(run_id)
    if result.get("reason") == "run not found":
        raise HTTPException(status_code=404, detail="Run not found")
    return result


@router.get("/runs/{run_id}/context-packet")
def get_run_context_packet(run_id: str, agent_id: str = "qa_agent") -> dict:
    run = RunManager().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    packet = build_context_packet(
        agent_id=agent_id,
        project_id=run.project_id,
        run_id=run.run_id,
        run_type=run.run_type,
        task=run.command,
        current_command=run.command,
    )
    return packet.model_dump()


@router.post("/test-retrieval")
def test_retrieval(payload: MemoryRetrievalRequest) -> dict:
    results = MemoryRetriever().retrieve(payload)
    packet = build_context_packet(
        agent_id=payload.agent_id,
        project_id=payload.project_id,
        run_id=None,
        run_type=payload.run_type,
        task=payload.query,
        current_command=payload.current_command or payload.query,
    )
    return {"results": [result.model_dump() for result in results], "context_packet": packet.model_dump()}
