from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from app.core.config import Settings, get_settings
from app.search_tools.schemas import SearchRequest, SearchResultPayload
from app.search_tools.source_formatter import mock_sources
from app.search_tools.search_store import SearchLogStore
from app.usage_sync.sync_store import SyncStore


EXA_SEARCH_URL = "https://api.exa.ai/search"
EXA_SEARCH_COST_PER_1000_REQUESTS = 7.0


async def run_exa_search(request: SearchRequest, settings: Settings | None = None, store: SyncStore | None = None) -> SearchResultPayload:
    active_settings = settings or get_settings()
    if request.mode != "live":
        sources = mock_sources(request.query, "exa_direct", request.max_results)
        _log_search_event(
            request=request,
            status="mock_fixture",
            sources=[source.model_dump() for source in sources],
            mock_fixture=True,
            estimated_cost=0.0,
        )
        return SearchResultPayload(
            research_used=True,
            search_provider_id="exa_direct",
            query_plan=[request.query],
            sources=sources,
            brief="Mock Exa Direct search result. No paid API call was made.",
            limitations=["Mock mode uses placeholder sources."],
            cost={"source": "mock", "estimated_usd": 0.0},
            mock_fixture=True,
        )
    if not request.allow_web_search:
        _log_search_event(request=request, status="skipped", error_type="search_disabled", error_message="allow_web_search must be true to call Exa.")
        raise HTTPException(status_code=400, detail="allow_web_search must be true to call Exa.")
    if not active_settings.allow_live_calls:
        _log_search_event(request=request, status="skipped", error_type="live_calls_disabled", error_message="ALLOW_LIVE_CALLS=false.")
        raise HTTPException(status_code=403, detail="Live provider calls are disabled. Set ALLOW_LIVE_CALLS=true for real Exa search.")
    if not active_settings.enable_exa_search:
        _log_search_event(request=request, status="skipped", error_type="provider_disabled", error_message="ENABLE_EXA_SEARCH=false.")
        raise HTTPException(status_code=400, detail="ENABLE_EXA_SEARCH=true is required for real Exa search.")
    if not active_settings.exa_api_key:
        _log_search_event(request=request, status="skipped", error_type="missing_api_key", error_message="EXA_API_KEY is not configured.")
        raise HTTPException(status_code=400, detail="EXA_API_KEY is not configured.")

    max_results = max(1, min(request.max_results, 10))
    payload = {
        "query": request.query,
        "type": "auto",
        "numResults": max_results,
        "contents": {"highlights": True},
    }
    started = datetime.now(UTC)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            EXA_SEARCH_URL,
            headers={"x-api-key": active_settings.exa_api_key, "Content-Type": "application/json"},
            json=payload,
        )
    if response.status_code >= 400:
        error_message = f"Exa search failed with status {response.status_code}."
        _log_search_event(
            request=request,
            status="failed",
            error_type="provider_http_error",
            error_message=error_message,
            estimated_cost=0.0,
        )
        _log_exa_search(
            request=request,
            settings=active_settings,
            store=store,
            request_id=response.headers.get("x-request-id"),
            estimated_cost=0.0,
            success=False,
            raw={"status_code": response.status_code, "body": response.text[:500]},
        )
        raise HTTPException(status_code=502, detail=error_message)
    data = response.json()
    request_id = str(data.get("requestId") or response.headers.get("x-request-id") or "")
    sources = [_source_from_exa_result(item) for item in data.get("results", []) if isinstance(item, dict)]
    estimated_cost = _estimate_exa_cost(max_results)
    _log_search_event(
        request=request,
        status="success",
        sources=[source.model_dump() for source in sources],
        estimated_cost=estimated_cost,
        request_id=request_id or None,
    )
    _log_exa_search(
        request=request,
        settings=active_settings,
        store=store,
        request_id=request_id or None,
        estimated_cost=estimated_cost,
        success=True,
        raw={"request": payload, "response": data, "duration_ms": int((datetime.now(UTC) - started).total_seconds() * 1000)},
    )
    return SearchResultPayload(
        research_used=True,
        search_provider_id="exa_direct",
        query_plan=[request.query],
        sources=sources,
        brief=f"Exa returned {len(sources)} source(s) using type=auto with highlights.",
        limitations=["Run-level Exa cost is estimated locally; official API-key usage sync provides authoritative billing when configured."],
        cost={"source": "search_tool_estimate", "estimated_usd": estimated_cost, "request_id": request_id or None},
        cache_hit=False,
    )


def _source_from_exa_result(item: dict) -> object:
    highlights = item.get("highlights") if isinstance(item.get("highlights"), list) else []
    snippet = "\n".join(str(value) for value in highlights[:3])
    url = str(item.get("url") or "")
    from app.search_tools.schemas import SearchSource

    return SearchSource(
        title=str(item.get("title") or url or "Untitled Exa result"),
        url=url,
        domain=urlparse(url).netloc or None,
        published_date=item.get("publishedDate"),
        retrieved_at=datetime.now(UTC).isoformat(),
        snippet=snippet,
        content_fetched=bool(highlights),
    )


def _estimate_exa_cost(max_results: int) -> float:
    extra_results = max(0, max_results - 10)
    return round((EXA_SEARCH_COST_PER_1000_REQUESTS / 1000) + (extra_results * 0.001 / 1000), 6)


def _log_exa_search(
    *,
    request: SearchRequest,
    settings: Settings,
    store: SyncStore | None,
    request_id: str | None,
    estimated_cost: float,
    success: bool,
    raw: dict,
) -> None:
    usage_store = store or SyncStore(settings)
    usage_store.create_record(
        provider="exa",
        source="provider_response",
        scope="run",
        project_id=request.project_id,
        run_id=request.run_id,
        agent_name=request.agent_name,
        request_id=request_id,
        requested_model="exa_search_auto",
        actual_model="exa_search_auto",
        model="exa_search_auto",
        total_tokens=0,
        safety_estimated_cost_usd=estimated_cost,
        provider_reported_cost_usd=None,
        currency="USD",
        sync_status="ok" if success else "error",
        provider_created_at=datetime.now(UTC).isoformat(),
        raw_usage_metadata={
            "search_type": "auto",
            "contents": "highlights",
            "max_results": request.max_results,
            "cost_source": "search_tool_estimate",
        },
        raw=raw,
    )


def _log_search_event(
    *,
    request: SearchRequest,
    status: str,
    sources: list[dict] | None = None,
    cache_hit: bool = False,
    mock_fixture: bool = False,
    error_type: str | None = None,
    error_message: str | None = None,
    estimated_cost: float = 0.0,
    request_id: str | None = None,
) -> None:
    SearchLogStore().append(
        {
            "run_id": request.run_id,
            "project_id": request.project_id,
            "provider_id": "exa_direct",
            "mode": request.mode,
            "query": request.query,
            "status": status,
            "source_count": len(sources or []),
            "sources": sources or [],
            "cache_hit": cache_hit,
            "mock_fixture": mock_fixture,
            "error_type": error_type,
            "error_message": error_message,
            "cost": {"estimated_usd": estimated_cost, "source": "search_tool_estimate"},
            "request_id": request_id,
        }
    )
