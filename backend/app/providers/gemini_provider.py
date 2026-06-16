from time import perf_counter

from app.core.config import get_settings
from app.core.cost_estimator import estimate_cost
from app.providers.base_provider import BaseProvider, ProviderResponse, build_fallback_response


class GeminiProvider(BaseProvider):
    """Guarded Gemini adapter. Search grounding is intentionally disabled."""

    name = "gemini"

    def complete(self, prompt: str, model: str) -> str:
        raise NotImplementedError("Gemini live calls are intentionally disabled in the MVP.")

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
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("Google GenAI SDK is not installed. Run pip install -r requirements.txt.") from exc

        client = genai.Client(api_key=settings.google_api_key)
        prompt = "\n".join(str(message.get("content", "")) for message in messages)
        response = await client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=max_output_tokens,
                temperature=temperature,
            ),
        )
        text = getattr(response, "text", "") or ""
        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", None) if usage else None
        output_tokens = getattr(usage, "candidates_token_count", None) if usage else None
        if input_tokens is None or output_tokens is None:
            return build_fallback_response(
                provider=self.name,
                model=model,
                messages=messages,
                text=text,
                max_output_tokens=max_output_tokens,
                started_at=started_at,
                raw_metadata={"usage_source": "estimated"},
            )

        estimate = estimate_cost(model, input_tokens, output_tokens)
        return ProviderResponse(
            provider=self.name,
            model=model,
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=0,
            estimated_cost_usd=estimate.estimated_cost_usd,
            latency_ms=round((perf_counter() - started_at) * 1000),
            raw_metadata={"usage_source": "provider"},
        )
