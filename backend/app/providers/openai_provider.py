from time import perf_counter

from app.core.config import get_settings
from app.core.cost_estimator import estimate_cost, estimate_messages_tokens
from app.providers.base_provider import BaseProvider, ProviderResponse, build_fallback_response


class OpenAIProvider(BaseProvider):
    """Guarded OpenAI adapter for dedicated provider tests only."""

    name = "openai"

    def complete(self, prompt: str, model: str) -> str:
        raise NotImplementedError("OpenAI live calls are intentionally disabled in the MVP.")

    async def generate(
        self,
        model: str,
        messages: list[dict],
        max_output_tokens: int = 300,
        temperature: float = 0.2,
        service_tier: str | None = None,
        response_format: dict | None = None,
    ) -> ProviderResponse:
        settings = get_settings()
        started_at = perf_counter()
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError("OpenAI SDK is not installed. Run pip install -r requirements.txt.") from exc

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        input_text = "\n".join(str(message.get("content", "")) for message in messages)
        request = {
            "model": model,
            "input": input_text,
            "max_output_tokens": max_output_tokens,
            "temperature": temperature,
        }
        if service_tier:
            request["service_tier"] = service_tier
        response = await client.responses.create(**request)

        text = getattr(response, "output_text", "") or ""
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None) if usage else None
        output_tokens = getattr(usage, "output_tokens", None) if usage else None
        cached_tokens = 0
        input_details = getattr(usage, "input_tokens_details", None) if usage else None
        if input_details:
            cached_tokens = getattr(input_details, "cached_tokens", 0) or 0

        if input_tokens is None or output_tokens is None:
            return build_fallback_response(
                provider=self.name,
                model=model,
                messages=messages,
                text=text,
                max_output_tokens=max_output_tokens,
                started_at=started_at,
                service_tier=service_tier,
                raw_metadata={"response_id": getattr(response, "id", None), "usage_source": "estimated"},
            )

        estimate = estimate_cost(model, input_tokens, output_tokens, cached_tokens, service_tier=service_tier)
        return ProviderResponse(
            provider=self.name,
            model=model,
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            estimated_cost_usd=estimate.estimated_cost_usd,
            latency_ms=round((perf_counter() - started_at) * 1000),
            raw_metadata={"response_id": getattr(response, "id", None), "usage_source": "provider"},
        )
