from fastapi import HTTPException

from app.core.config import Settings, get_settings
from app.core.cost_estimator import assert_call_budget, estimate_messages_tokens
from app.providers.base_provider import ProviderResponse
from app.providers.gemini_provider import GeminiProvider
from app.providers.mock_provider import MockProvider
from app.providers.openai_provider import OpenAIProvider
from app.providers.openrouter_provider import OpenRouterProvider
from app.storage.usage_store import UsageStore


PROVIDERS = {
    "mock": MockProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "openrouter": OpenRouterProvider,
}


async def generate_with_provider(
    *,
    provider: str,
    model: str,
    mode: str,
    messages: list[dict],
    max_output_tokens: int = 300,
    temperature: float = 0.2,
    service_tier: str | None = None,
    run_id: str | None = None,
    task_id: str | None = None,
    agent_name: str | None = None,
    agent_role: str | None = None,
    project_id: str | None = None,
    request_type: str = "provider_test",
    settings: Settings | None = None,
    usage_store: UsageStore | None = None,
) -> tuple[ProviderResponse, str]:
    settings = settings or get_settings()
    usage_store = usage_store or UsageStore(settings)
    provider = provider.lower()
    mode = mode.lower()

    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
    if mode not in {"mock", "live"}:
        raise HTTPException(status_code=400, detail="mode must be 'mock' or 'live'.")

    if max_output_tokens > settings.max_output_tokens_per_call:
        raise HTTPException(
            status_code=400,
            detail=f"max_output_tokens exceeds MAX_OUTPUT_TOKENS_PER_CALL={settings.max_output_tokens_per_call}.",
        )

    input_tokens = estimate_messages_tokens(messages)
    assert_call_budget(model, input_tokens, max_output_tokens, service_tier=service_tier)

    effective_provider = provider
    if mode == "mock":
        effective_provider = "mock"
    else:
        settings.validate_provider_ready(provider)

    provider_instance = PROVIDERS[effective_provider]()

    try:
        response = await provider_instance.generate(
            model=model,
            messages=messages,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            service_tier=service_tier,
        )
        usage_log_id = usage_store.log_call(
            run_id=run_id,
            task_id=task_id,
            agent_name=agent_name,
            agent_role=agent_role,
            provider=response.provider if mode == "mock" else provider,
            model=response.model,
            mode=mode,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cached_tokens=response.cached_tokens,
            estimated_cost_usd=response.estimated_cost_usd,
            latency_ms=response.latency_ms,
            success=True,
            request_type=request_type,
            metadata={"effective_provider": effective_provider, "project_id": project_id, **response.raw_metadata},
        )
        return response, usage_log_id
    except HTTPException:
        raise
    except Exception as exc:
        usage_log_id = usage_store.log_call(
            run_id=run_id,
            task_id=task_id,
            agent_name=agent_name,
            agent_role=agent_role,
            provider=provider,
            model=model,
            mode=mode,
            input_tokens=input_tokens,
            output_tokens=0,
            cached_tokens=0,
            estimated_cost_usd=0,
            latency_ms=0,
            success=False,
            error_message=str(exc),
            request_type=request_type,
            metadata={"effective_provider": effective_provider, "project_id": project_id},
        )
        raise HTTPException(status_code=502, detail=f"Provider call failed. usage_log_id={usage_log_id}") from exc
