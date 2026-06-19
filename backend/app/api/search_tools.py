from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.search_tools.exa_client import run_exa_search
from app.search_tools.gemini_search_client import run_gemini_google_search
from app.search_tools.openai_search_client import run_openai_web_search
from app.search_tools.registry_loader import SearchRegistryLoader
from app.search_tools.schemas import SearchRequest, SearchSelectionRequest
from app.search_tools.search_selector import SearchSelector
from app.search_tools.search_store import SearchLogStore

router = APIRouter(prefix="/api/search-tools", tags=["search-tools"])


@router.get("/providers")
def list_search_providers() -> dict:
    return SearchRegistryLoader().status()


@router.get("/status")
def search_status() -> dict:
    return SearchRegistryLoader().status()


@router.post("/test")
def test_search_provider(payload: SearchSelectionRequest) -> dict:
    selection = SearchSelector().select(payload)
    record = SearchLogStore().append(
        {
            "kind": "selection_test",
            "query": payload.query,
            "mode": payload.mode,
            "allow_web_search": payload.allow_web_search,
            "selection": selection.model_dump(),
        }
    )
    return {"selection": selection.model_dump(), "log": record}


@router.post("/search")
async def search(payload: SearchRequest) -> dict:
    selection = SearchSelector().select(
        SearchSelectionRequest(
            query=payload.query,
            allow_web_search=payload.allow_web_search,
            mode=payload.mode,
            explicit_provider_id=payload.provider_id,
            max_results=payload.max_results,
        )
    )
    if selection.search_unavailable or not selection.selected_provider_id:
        raise HTTPException(status_code=400, detail=selection.reason)
    if selection.selected_provider_id == "exa_direct":
        result = await run_exa_search(payload.model_copy(update={"provider_id": "exa_direct"}))
    elif selection.selected_provider_id == "openai_web_search":
        result = await run_openai_web_search(payload.model_copy(update={"provider_id": "openai_web_search"}))
    elif selection.selected_provider_id == "gemini_google_search":
        result = await run_gemini_google_search(payload.model_copy(update={"provider_id": "gemini_google_search"}))
    else:
        raise HTTPException(status_code=400, detail="Unsupported search provider.")
    SearchLogStore().append(
        {
            "kind": "search",
            "query": payload.query,
            "mode": payload.mode,
            "provider_id": selection.selected_provider_id,
            "source_count": len(result.sources),
            "cost": result.cost,
        }
    )
    return result.model_dump()


@router.get("/logs/recent")
def recent_search_logs(limit: int = 25) -> dict:
    return {"logs": SearchLogStore().recent(limit)}
