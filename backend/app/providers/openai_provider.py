import json
from time import perf_counter
from typing import Any

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
        }
        if _supports_temperature(model):
            request["temperature"] = temperature
        if service_tier:
            request["service_tier"] = service_tier
        text_format = _responses_text_format(response_format)
        if text_format:
            request["text"] = text_format
        response = await client.responses.create(**request)

        text = _extract_response_text(response)
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
                raw_metadata=_response_metadata(response, response_format=response_format, usage_source="estimated"),
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
            raw_metadata=_response_metadata(response, response_format=response_format, usage_source="provider"),
        )


def _supports_temperature(model: str) -> bool:
    return not model.startswith("gpt-5.5")


def _responses_text_format(response_format: dict[str, Any] | None) -> dict[str, Any] | None:
    if not response_format:
        return None
    if "format" in response_format:
        return response_format
    if response_format.get("type") == "json_object":
        return {"format": {"type": "json_object"}}
    if response_format.get("type") == "json_schema":
        json_schema = response_format.get("json_schema") or {}
        schema = json_schema.get("schema")
        if not schema:
            return None
        return {
            "format": {
                "type": "json_schema",
                "name": json_schema.get("name") or "structured_response",
                "schema": schema,
                "strict": bool(json_schema.get("strict", True)),
            }
        }
    return None


def _extract_response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)
    output_parsed = getattr(response, "output_parsed", None)
    if output_parsed is not None:
        return json.dumps(output_parsed)

    chunks: list[str] = []
    for item in _iter_values(getattr(response, "output", None)):
        for content in _iter_values(_get_value(item, "content")):
            parsed = _get_value(content, "parsed")
            if parsed is not None:
                chunks.append(json.dumps(parsed))
                continue
            text = _get_value(content, "text")
            if text:
                chunks.append(str(text))
    return "\n".join(chunks)


def _response_metadata(response: Any, *, response_format: dict[str, Any] | None, usage_source: str) -> dict[str, Any]:
    incomplete_details = getattr(response, "incomplete_details", None)
    return {
        "response_id": getattr(response, "id", None),
        "usage_source": usage_source,
        "status": getattr(response, "status", None),
        "incomplete_details": _safe_object(incomplete_details),
        "requested_response_format": response_format or {},
        "content_source": "output_text_or_output_parts",
    }


def _iter_values(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return list(value) if isinstance(value, tuple) else [value]


def _get_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _safe_object(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return value
    try:
        return value.model_dump()
    except Exception:
        return str(value)
