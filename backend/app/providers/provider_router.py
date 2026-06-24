import re
from typing import Any

from fastapi import HTTPException

from app.core.config import Settings, get_settings
from app.core.cost_estimator import assert_call_budget, estimate_messages_tokens
from app.providers.base_provider import ProviderResponse
from app.providers.gemini_provider import GeminiProvider
from app.providers.mock_provider import MockProvider
from app.providers.openai_provider import OpenAIProvider
from app.providers.openrouter_provider import OpenRouterProvider
from app.storage.usage_store import UsageStore
from app.usage_sync.reconciliation_service import store_provider_response_usage
from app.usage_sync.openrouter_usage_sync import sync_openrouter_generation


PROVIDERS = {
    "mock": MockProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "openrouter": OpenRouterProvider,
}


_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"key_[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)(authorization\s*[:=]\s*)[^\s,;}]+"),
    re.compile(r"(?i)((?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s,;}]+"),
]


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
    response_format: dict | None = None,
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

    if request_type == "real_coding_agent":
        output_limit = settings.real_coding_max_output_tokens
    elif request_type == "business_builder_live_planning":
        output_limit = settings.business_builder_live_max_output_tokens
    else:
        output_limit = settings.max_output_tokens_per_call
    if max_output_tokens > output_limit:
        raise HTTPException(
            status_code=400,
            detail=f"max_output_tokens exceeds configured output token limit={output_limit}.",
        )

    input_tokens = estimate_messages_tokens(messages)
    assert_call_budget(model, input_tokens, max_output_tokens, service_tier=service_tier, max_output_tokens_per_call=output_limit)

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
            response_format=response_format,
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
        if mode == "live":
            store_provider_response_usage(
                provider=provider,
                model=response.model,
                run_id=run_id,
                project_id=project_id,
                agent_name=agent_name,
                request_id=usage_log_id,
                response_id=response.raw_metadata.get("response_id"),
                generation_id=response.raw_metadata.get("generation_id"),
                requested_model=model,
                actual_model=response.model,
                openrouter_provider_name=response.raw_metadata.get("effective_provider"),
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cached_tokens=response.cached_tokens,
                reasoning_tokens=response.raw_metadata.get("reasoning_tokens"),
                safety_estimated_cost_usd=response.estimated_cost_usd,
                provider_reported_cost_usd=response.raw_metadata.get("provider_reported_cost_usd"),
                raw=response.raw_metadata,
                settings=settings,
            )
            if provider == "openrouter" and response.raw_metadata.get("generation_id"):
                await sync_openrouter_generation(
                    generation_id=response.raw_metadata["generation_id"],
                    run_id=run_id,
                    project_id=project_id,
                    agent_name=agent_name,
                    requested_model=model,
                    settings=settings,
                )
        return response, usage_log_id
    except HTTPException:
        raise
    except Exception as exc:
        provider_error = _provider_error_payload(exc, provider=provider, model=model)
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
            error_message=provider_error["summary"],
            request_type=request_type,
            metadata={
                "effective_provider": effective_provider,
                "project_id": project_id,
                "provider_error": provider_error,
            },
        )
        raise HTTPException(
            status_code=502,
            detail=f"Provider call failed for {provider}/{model}: {provider_error['summary']}. usage_log_id={usage_log_id}",
        ) from exc


def _provider_error_payload(exc: Exception, *, provider: str, model: str) -> dict[str, Any]:
    response = getattr(exc, "response", None)
    status_code = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
    code = getattr(exc, "code", None) or getattr(exc, "error_code", None)
    body_preview = _response_body_preview(response)
    message = _truncate(_sanitize_provider_error(str(exc) or exc.__class__.__name__), 900)
    summary_parts = [f"{exc.__class__.__name__}: {message}"]
    if status_code:
        summary_parts.append(f"status={status_code}")
    if code:
        summary_parts.append(f"code={_truncate(_sanitize_provider_error(str(code)), 120)}")
    if body_preview:
        summary_parts.append(f"body={body_preview}")

    summary = _truncate(" | ".join(summary_parts), 1200)
    return {
        "provider": provider,
        "model": model,
        "type": exc.__class__.__name__,
        "message": message,
        "status_code": status_code,
        "code": _truncate(_sanitize_provider_error(str(code)), 120) if code else None,
        "body_preview": body_preview,
        "summary": summary,
    }


def _response_body_preview(response: Any) -> str | None:
    if response is None:
        return None
    text = getattr(response, "text", None)
    if not text and hasattr(response, "json"):
        try:
            text = str(response.json())
        except Exception:
            text = None
    if not text:
        return None
    return _truncate(_sanitize_provider_error(str(text)), 500)


def _sanitize_provider_error(value: str) -> str:
    cleaned = " ".join(value.replace("\r", " ").replace("\n", " ").split())
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub(lambda match: f"{match.group(1)}[redacted]" if match.lastindex else "[redacted]", cleaned)
    return cleaned


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."
