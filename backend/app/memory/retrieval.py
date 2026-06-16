from app.core.config import get_settings
from app.core.models import MemorySummary
from app.memory.core_memory import get_core_memory
from app.memory.current_state import get_current_state
from app.memory.vector_memory import LocalVectorMemory


def retrieve_memory(query: str) -> MemorySummary:
    settings = get_settings()
    vector_memory = LocalVectorMemory(str(settings.vector_path))
    snippets = vector_memory.search(query)
    return MemorySummary(
        core_memory=get_core_memory(),
        current_state=get_current_state(),
        retrieved_snippets=snippets,
        vector_store_path=str(settings.vector_path),
    )
