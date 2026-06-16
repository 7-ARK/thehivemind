from fastapi import APIRouter

from app.core.models import MemorySummary
from app.memory.retrieval import retrieve_memory

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/summary", response_model=MemorySummary)
def get_memory_summary() -> MemorySummary:
    return retrieve_memory("TheHiveMind MVP orchestration")

