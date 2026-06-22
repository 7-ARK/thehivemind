from __future__ import annotations

from datetime import UTC, datetime

from app.core.config import Settings, get_settings
from app.memory.memory_index import cosine, sparse_vector, tokenize
from app.memory.memory_policies import active_constraints_from_command
from app.memory.memory_store import MemoryStore
from app.memory.schemas import MemoryItem, MemoryRetrievalRequest, MemorySearchResult

RESEARCH_TYPES = {"research_brief", "research_source_summary"}
PLANNING_TYPES = {"agent_plan", "next_step"}


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
        query_kind = classify_query(query, request.agent_id, request.run_type)
        candidates = [
            item
            for item in self.store.items(project_id=request.project_id, include_global=True)
            if self._allowed_for_agent(item, request.agent_id)
            and not (item.scope == "project" and item.project_id != request.project_id)
        ]
        live_source_available = any(self._is_live_source_memory(item) for item in candidates)
        for item in candidates:
            if not self._allowed_for_agent(item, request.agent_id):
                continue
            if item.scope == "project" and item.project_id != request.project_id:
                continue
            score, why = self._score(item, query_vector, query_tokens, request, query_kind, live_source_available)
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
        query_kind: str,
        live_source_available: bool,
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
        score = self._apply_query_boosts(score, why, item, query_kind, live_source_available)
        if not why:
            why.append("low relevance")
        return score, why

    def _apply_query_boosts(self, score: float, why: list[str], item: MemoryItem, query_kind: str, live_source_available: bool) -> float:
        source_count = _int_metadata(item, "source_count")
        search_unavailable = _bool_metadata(item, "search_unavailable")
        mock_fixture = _bool_metadata(item, "mock_fixture")
        has_provider = bool(item.search_provider or item.metadata.get("provider_id"))
        has_source_urls = bool(item.source_urls)

        if query_kind in {"research_query", "source_query"}:
            if item.memory_type == "research_source_summary":
                score += 0.75
                why.append("boosted: research_source_summary")
            if item.memory_type == "research_brief":
                score += 0.38
                why.append("boosted: research_brief")
            if source_count > 0:
                score += 0.50
                why.append("boosted: source_count > 0")
            if has_provider or has_source_urls:
                score += 0.42
                why.append("boosted: previous live Exa source")
            if search_unavailable or source_count == 0:
                score -= 0.55
                why.append("down-ranked: skipped search")
            if mock_fixture and live_source_available:
                score -= 0.22
                why.append("down-ranked: mock fixture")
            if item.memory_type in PLANNING_TYPES or item.memory_type == "model_selection":
                score -= 0.28
                why.append("down-ranked: planning artifact for research query")

        if query_kind == "website_update_query":
            if item.memory_type in RESEARCH_TYPES:
                score += 0.22
                why.append(f"boosted: {item.memory_type}")
            if item.memory_type in {"file_change_summary", "project_state", "qa_warning", "safety_constraint"}:
                score += 0.18
                why.append(f"boosted: {item.memory_type}")
            if item.memory_type in RESEARCH_TYPES and (source_count > 0 or has_provider or has_source_urls):
                score += 0.18
                why.append("boosted: previous live Exa source")
            if item.memory_type in RESEARCH_TYPES and (search_unavailable or source_count == 0):
                score -= 0.18
                why.append("down-ranked: skipped search")

        if query_kind == "model_routing_query" and item.memory_type == "model_selection":
            score += 0.35
            why.append("boosted: model_selection for routing query")
        elif query_kind != "model_routing_query" and item.memory_type == "model_selection":
            score -= 0.10

        if query_kind == "planning_query" and item.memory_type in PLANNING_TYPES:
            score += 0.28
            why.append("boosted: planning memory")
        elif query_kind not in {"planning_query", "next_step_query"} and item.memory_type in PLANNING_TYPES:
            score -= 0.08

        if query_kind == "qa_query" and item.memory_type == "qa_warning":
            score += 0.30
            why.append("boosted: QA warning")
        if query_kind == "file_history_query" and item.memory_type == "file_change_summary":
            score += 0.32
            why.append("boosted: file_change_summary")
        return score

    def _is_live_source_memory(self, item: MemoryItem) -> bool:
        return (
            item.memory_type == "research_source_summary"
            and _int_metadata(item, "source_count") > 0
            and not _bool_metadata(item, "search_unavailable")
            and not _bool_metadata(item, "mock_fixture")
            and bool(item.search_provider or item.source_urls)
        )

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


def classify_query(query: str, agent_id: str = "", run_type: str = "") -> str:
    text = f"{query} {agent_id} {run_type}".lower()
    if any(term in text for term in ("source", "sources", "exa", "citation", "url", "research used")):
        return "source_query"
    if any(term in text for term in ("research", "competitor", "market", "themes", "summarize")):
        return "research_query"
    if any(term in text for term in ("homepage", "landing page", "website copy", "hero", "update website", "improve homepage")):
        return "website_update_query"
    if any(term in text for term in ("model", "routing", "gpt", "gemini", "openrouter", "provider")):
        return "model_routing_query"
    if any(term in text for term in ("qa", "validate", "warning", "risk", "review")):
        return "qa_query"
    if any(term in text for term in ("file", "changed", "updated", "history", "workspace")):
        return "file_history_query"
    if any(term in text for term in ("next step", "continue", "plan", "workflow", "task breakdown")):
        return "planning_query"
    return "general"


def _bool_metadata(item: MemoryItem, key: str) -> bool:
    value = item.metadata.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes"}
    return bool(value)


def _int_metadata(item: MemoryItem, key: str) -> int:
    value = item.metadata.get(key, 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
