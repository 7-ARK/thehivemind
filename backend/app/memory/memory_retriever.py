from __future__ import annotations

from datetime import UTC, datetime

from app.core.config import Settings, get_settings
from app.memory.memory_index import cosine, sparse_vector, tokenize
from app.memory.memory_policies import active_constraints_from_command
from app.memory.memory_store import MemoryStore
from app.memory.schemas import MemoryItem, MemoryRetrievalRequest, MemorySearchResult


class MemoryRetriever:
    def __init__(self, settings: Settings | None = None, store: MemoryStore | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = store or MemoryStore(self.settings)

    def retrieve(self, request: MemoryRetrievalRequest) -> list[MemorySearchResult]:
        if not self.settings.enable_vector_memory:
            return []
        query = " ".join([request.query, request.current_command, request.agent_id, request.run_type])
        query_vector = sparse_vector(query)
        query_tokens = set(tokenize(query))
        results: list[MemorySearchResult] = []
        for item in self.store.items(project_id=request.project_id, include_global=True):
            if not self._allowed_for_agent(item, request.agent_id):
                continue
            if item.scope == "project" and item.project_id != request.project_id:
                continue
            score, why = self._score(item, query_vector, query_tokens, request)
            if score <= 0:
                continue
            results.append(MemorySearchResult(item=item, score=round(score, 4), why_selected=why))
        deduped = self._dedupe(sorted(results, key=lambda result: result.score, reverse=True))
        return self._apply_budget(deduped, request.max_items, request.max_tokens)

    def _score(
        self,
        item: MemoryItem,
        query_vector: dict[str, float],
        query_tokens: set[str],
        request: MemoryRetrievalRequest,
    ) -> tuple[float, list[str]]:
        similarity = cosine(query_vector, item.sparse_vector)
        tag_match_count = len(set(item.tags) & query_tokens)
        tag_score = min(1.0, tag_match_count / 3)
        project_score = 1.0 if item.scope == "global" or item.project_id == request.project_id else 0.0
        recency = max(0.0, min(1.0, item.recency_score))
        importance = item.importance / 5
        trust = max(0.0, min(1.0, item.trust_score))
        score = (similarity * 0.45) + (tag_score * 0.20) + (recency * 0.15) + (importance * 0.15) + (trust * 0.05)
        score *= project_score
        why = []
        if similarity > 0:
            why.append(f"similarity {similarity:.2f}")
        if tag_match_count:
            why.append(f"tag match: {tag_match_count}")
        if item.scope == "global":
            why.append("global core memory")
        elif item.project_id == request.project_id:
            why.append("project match")
        if item.importance >= 4:
            why.append("high importance")
        if not why:
            why.append("low relevance")
        return score, why

    def _allowed_for_agent(self, item: MemoryItem, agent_id: str) -> bool:
        if item.blocked_agents and agent_id in item.blocked_agents:
            return False
        if item.allowed_agents and agent_id not in item.allowed_agents:
            return False
        return item.should_inject_by_default

    def _dedupe(self, results: list[MemorySearchResult]) -> list[MemorySearchResult]:
        seen = set()
        deduped = []
        for result in results:
            key = result.item.hash or result.item.id
            if key in seen:
                continue
            seen.add(key)
            deduped.append(result)
        return deduped

    def _apply_budget(self, results: list[MemorySearchResult], max_items: int, max_tokens: int) -> list[MemorySearchResult]:
        selected = []
        tokens = 0
        for result in results:
            if len(selected) >= max_items:
                break
            next_tokens = tokens + result.item.token_estimate
            if next_tokens > max_tokens and selected:
                continue
            selected.append(result)
            tokens = next_tokens
        return selected


def default_retrieval_request(
    *,
    project_id: str | None,
    query: str,
    agent_id: str,
    run_type: str,
    current_command: str,
    settings: Settings | None = None,
) -> MemoryRetrievalRequest:
    active_settings = settings or get_settings()
    return MemoryRetrievalRequest(
        project_id=project_id,
        query=query,
        agent_id=agent_id,
        run_type=run_type,
        current_command=current_command,
        max_items=active_settings.memory_top_k,
        max_tokens=active_settings.memory_max_tokens_per_agent,
    )


def constraints_for_packet(command: str, run_type: str) -> list[str]:
    return active_constraints_from_command(command, run_type)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
