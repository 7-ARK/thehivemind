from time import perf_counter

from app.providers.base_provider import BaseProvider, build_fallback_response


class MockProvider(BaseProvider):
    """Deterministic provider used by default for local demos and interviews."""

    name = "mock"

    def complete(self, prompt: str, model: str) -> str:
        return f"Mock response from {model}: {prompt[:160]}"

    async def generate(
        self,
        model: str,
        messages: list[dict],
        max_output_tokens: int = 300,
        temperature: float = 0.2,
        service_tier: str | None = None,
        response_format: dict | None = None,
    ):
        started_at = perf_counter()
        prompt = "\n".join(str(message.get("content", "")) for message in messages)
        text = f"TheHiveMind provider test worked in mock mode for {model}. Prompt received: {prompt[:80]}"
        return build_fallback_response(
            provider=self.name,
            model=model,
            messages=messages,
            text=text,
            max_output_tokens=max_output_tokens,
            started_at=started_at,
            service_tier=service_tier,
            raw_metadata={"mock": True, "temperature": temperature},
        )
