from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.model_registry import MODEL_REGISTRY
from app.providers.provider_router import generate_with_provider

router = APIRouter(prefix="/api/providers", tags=["providers"])


class ProviderTestRequest(BaseModel):
    provider: Literal["mock", "openai", "gemini", "openrouter"]
    model: str
    mode: Literal["mock", "live"] = "mock"
    prompt: str = Field(..., min_length=1, max_length=4000)
    max_output_tokens: int = Field(default=80, ge=1)
    temperature: float = Field(default=0.2, ge=0, le=2)
    service_tier: str | None = None


class ProviderTestResponse(BaseModel):
    success: bool
    provider: str
    model: str
    mode: str
    output: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    estimated_cost_usd: float
    latency_ms: int
    usage_log_id: str
    safety: dict


@router.post("/test", response_model=ProviderTestResponse)
async def test_provider(payload: ProviderTestRequest) -> ProviderTestResponse:
    settings = get_settings()
    response, usage_log_id = await generate_with_provider(
        provider=payload.provider,
        model=payload.model,
        mode=payload.mode,
        messages=[{"role": "user", "content": payload.prompt}],
        max_output_tokens=payload.max_output_tokens,
        temperature=payload.temperature,
        service_tier=payload.service_tier,
        request_type="provider_test",
        settings=settings,
    )
    return ProviderTestResponse(
        success=True,
        provider=payload.provider if payload.mode == "live" else "mock",
        model=response.model,
        mode=payload.mode,
        output=response.text,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cached_tokens=response.cached_tokens,
        estimated_cost_usd=response.estimated_cost_usd,
        latency_ms=response.latency_ms,
        usage_log_id=usage_log_id,
        safety={
            "live_calls_allowed": settings.is_live_allowed(),
            "max_output_tokens": payload.max_output_tokens,
            "max_cost_per_call_usd": settings.max_cost_per_call_usd,
            "search_enabled": False,
        },
    )


@router.get("/status")
def provider_status() -> dict:
    settings = get_settings()
    return {
        "providers": {
            "openai": {"configured": bool(settings.openai_api_key), "search_enabled": settings.enable_openai_web_search},
            "gemini": {"configured": bool(settings.google_api_key), "search_enabled": settings.enable_gemini_grounding},
            "openrouter": {
                "configured": bool(settings.openrouter_api_key),
                "search_enabled": settings.enable_openrouter_search,
            },
        },
        "live_calls_allowed": settings.is_live_allowed(),
        "default_models": {
            "ceo_model": settings.ceo_model,
            "ceo_service_tier": settings.ceo_service_tier,
            "model_selector_model": settings.model_selector_model,
            "cheap_worker_model": settings.cheap_worker_model,
            "cheap_search_worker_model": settings.cheap_search_worker_model,
            "openrouter_default_model": settings.openrouter_default_model,
        },
        "limits": {
            "max_input_tokens_per_call": settings.max_input_tokens_per_call,
            "max_output_tokens_per_call": settings.max_output_tokens_per_call,
            "max_cost_per_call_usd": settings.max_cost_per_call_usd,
            "max_cost_per_run_usd": settings.max_cost_per_run_usd,
        },
        "registered_models": {
            key: value.model_dump(exclude_none=True) for key, value in MODEL_REGISTRY.items()
        },
    }
