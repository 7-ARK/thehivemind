from abc import ABC, abstractmethod
from time import perf_counter
from typing import Any

from pydantic import BaseModel, Field

from app.core.cost_estimator import estimate_cost, estimate_messages_tokens


class ProviderResponse(BaseModel):
    provider: str
    model: str
    text: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    estimated_cost_usd: float
    latency_ms: int
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class BaseProvider(ABC):
    name: str

    @abstractmethod
    async def generate(
        self,
        model: str,
        messages: list[dict],
        max_output_tokens: int = 300,
        temperature: float = 0.2,
        service_tier: str | None = None,
    ) -> ProviderResponse:
        ...


def build_fallback_response(
    *,
    provider: str,
    model: str,
    messages: list[dict],
    text: str,
    max_output_tokens: int,
    started_at: float,
    service_tier: str | None = None,
    raw_metadata: dict[str, Any] | None = None,
) -> ProviderResponse:
    input_tokens = estimate_messages_tokens(messages)
    output_tokens = min(max_output_tokens, max(1, len(text) // 4))
    estimate = estimate_cost(model, input_tokens, output_tokens, service_tier=service_tier)
    return ProviderResponse(
        provider=provider,
        model=model,
        text=text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=0,
        estimated_cost_usd=estimate.estimated_cost_usd,
        latency_ms=round((perf_counter() - started_at) * 1000),
        raw_metadata=raw_metadata or {},
    )
