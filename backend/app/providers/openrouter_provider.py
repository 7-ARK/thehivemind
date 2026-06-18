from time import perf_counter

import httpx

from app.core.config import get_settings
from app.core.cost_estimator import estimate_cost, estimate_messages_tokens
from app.providers.base_provider import BaseProvider, ProviderResponse, build_fallback_response


class OpenRouterProvider(BaseProvider):
    """Guarded OpenRouter chat-completions adapter with plugins/search disabled."""

    name = "openrouter"

    def complete(self, prompt: str, model: str) -> str:
        raise NotImplementedError("OpenRouter live calls are intentionally disabled in the MVP.")

    async def generate(
        self,
        model: str,
        messages: list[dict],
        max_output_tokens: int = 300,
        temperature: float = 0.2,
        service_tier: str | None = None,
    ) -> ProviderResponse:
        settings = get_settings()
        started_at = perf_counter()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost",
                    "X-Title": "TheHiveMind Provider Test",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_output_tokens,
                    "temperature": temperature,
                },
            )
            response.raise_for_status()
            payload = response.json()

        choice = (payload.get("choices") or [{}])[0]
        text = ((choice.get("message") or {}).get("content")) or ""
        usage = payload.get("usage") or {}
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        if input_tokens is None or output_tokens is None:
            return build_fallback_response(
                provider=self.name,
                model=model,
                messages=messages,
                text=text,
                max_output_tokens=max_output_tokens,
                started_at=started_at,
                raw_metadata={"usage_source": "estimated", "response_id": payload.get("id")},
            )

        estimated_cost = usage.get("cost")
        if estimated_cost is None:
            estimated_cost = estimate_cost(model, input_tokens, output_tokens).estimated_cost_usd

        return ProviderResponse(
            provider=self.name,
            model=model,
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=int(usage.get("cached_tokens") or 0),
            estimated_cost_usd=round(float(estimated_cost), 6),
            latency_ms=round((perf_counter() - started_at) * 1000),
            raw_metadata={
                "usage_source": "provider",
                "response_id": payload.get("id"),
                "generation_id": payload.get("id"),
                "provider_reported_cost_usd": round(float(estimated_cost), 6),
                "reasoning_tokens": usage.get("reasoning_tokens"),
                "effective_provider": payload.get("provider"),
            },
        )
