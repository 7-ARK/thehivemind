from app.core.config import get_settings
from app.core.models import MemorySnippet, MemorySummary
from app.memory.core_memory import get_core_memory
from app.memory.current_state import get_current_state
from app.memory.memory_retriever import MemoryRetriever
from app.memory.schemas import MemoryRetrievalRequest
from app.memory.vector_memory import LocalVectorMemory


def retrieve_memory(query: str, project_id: str | None = None, agent_id: str = "qa_agent", run_type: str = "general") -> MemorySummary:
    settings = get_settings()
    snippets = []
    if settings.enable_vector_memory and (settings.memory_use_in_mock or settings.memory_use_in_live):
        results = MemoryRetriever(settings).retrieve(
            MemoryRetrievalRequest(
                project_id=project_id,
                query=query,
                current_command=query,
                agent_id=agent_id,
                run_type=run_type,
                max_items=settings.memory_top_k,
                max_tokens=settings.memory_max_tokens_per_agent,
            )
        )
        snippets = [
            MemorySnippet(
                title=result.item.title,
                content=result.item.summary or result.item.content,
                relevance_score=result.score,
            )
            for result in results
        ]
    if not snippets:
        vector_memory = LocalVectorMemory(str(settings.vector_path))
        snippets = vector_memory.search(query)
    return MemorySummary(
        core_memory=get_core_memory(),
        current_state=get_current_state(),
        retrieved_snippets=snippets,
        vector_store_path=str(settings.memory_path),
    )


def disabled_memory_summary() -> MemorySummary:
    settings = get_settings()
    return MemorySummary(
        core_memory=get_core_memory(),
        current_state=get_current_state(),
        retrieved_snippets=[],
        vector_store_path=str(settings.memory_path),
    )
