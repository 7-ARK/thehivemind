from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.model_registry.availability_service import ModelAvailabilityService
from app.model_registry.openrouter_discovery import OpenRouterDiscoveryService
from app.model_registry.registry_loader import ModelRegistryLoader
from app.model_registry.schemas import ModelSelectionRequest, ModelSelectionResult
from app.model_registry.selector_service import DynamicModelSelector

router = APIRouter(prefix="/api/model-registry", tags=["model-registry"])


@router.get("/models")
def list_models() -> dict:
    loader = ModelRegistryLoader()
    return {"models": [model.model_dump() for model in loader.models()]}


@router.get("/models/{model_id:path}")
def get_model(model_id: str) -> dict:
    model = ModelRegistryLoader().get_model(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found.")
    return model.model_dump()


@router.get("/summary")
def model_registry_summary() -> dict:
    loader = ModelRegistryLoader()
    models = loader.models()
    return {
        "models_count": len(models),
        "providers": sorted({model.provider for model in models}),
        "active_models": [model.id for model in models if model.enabled and model.status == "active"],
        "blocked_by_default": [model.id for model in models if model.blocked_by_default],
        "openrouter_discovery": OpenRouterDiscoveryService().summary(),
        "notes": loader.notes(),
    }


@router.get("/availability")
def model_availability(mode: str = "mock", search_required: bool = False) -> dict:
    service = ModelAvailabilityService()
    return {"availability": [item.model_dump() for item in service.all(mode=mode, search_required=search_required)]}


@router.post("/select", response_model=ModelSelectionResult)
def select_model(payload: ModelSelectionRequest) -> ModelSelectionResult:
    try:
        return DynamicModelSelector().select(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/discovery/openrouter")
def openrouter_discovery_cache() -> dict:
    return OpenRouterDiscoveryService().read_cache()


@router.post("/discovery/openrouter/sync")
async def sync_openrouter_discovery() -> dict:
    try:
        cache = await OpenRouterDiscoveryService().sync()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenRouter discovery sync failed: {exc}") from exc
    return {"status": "ok", "summary": OpenRouterDiscoveryService().summary(), "models_count": len(cache.get("models", []))}


@router.get("/discovery/openrouter/summary")
def openrouter_discovery_summary() -> dict:
    return OpenRouterDiscoveryService().summary()
