from time import perf_counter
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.cost_estimator import estimate_cost
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
        response_format: dict | None = None,
    ) -> ProviderResponse:
        settings = get_settings()
        started_at = perf_counter()
        request_body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_output_tokens,
            "temperature": temperature,
        }
        if response_format:
            request_body["response_format"] = response_format
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost",
                    "X-Title": "TheHiveMind Provider Test",
                },
                json=request_body,
            )
            response.raise_for_status()
            http_status = response.status_code
            payload = response.json()

        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content")
        tool_arguments = _first_tool_call_arguments(message)
        text = content or tool_arguments or ""
        content_source = "message.content" if content else ("tool_arguments" if tool_arguments else "empty")
        usage = payload.get("usage") or {}
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        safe_metadata = _safe_response_metadata(
            payload=payload,
            choice=choice,
            message=message,
            text=text,
            response_format=response_format,
            max_output_tokens=max_output_tokens,
            usage_source="estimated" if input_tokens is None or output_tokens is None else "provider",
            http_status=http_status,
            output_tokens=output_tokens,
            reasoning_tokens=usage.get("reasoning_tokens"),
            content_source=content_source,
        )
        if input_tokens is None or output_tokens is None:
            return build_fallback_response(
                provider=self.name,
                model=model,
                messages=messages,
                text=text,
                max_output_tokens=max_output_tokens,
                started_at=started_at,
                raw_metadata=safe_metadata,
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
                "provider_reported_cost_usd": round(float(estimated_cost), 6),
                "reasoning_tokens": usage.get("reasoning_tokens"),
                "effective_provider": payload.get("provider"),
                **safe_metadata,
            },
        )


def _first_tool_call_arguments(message: dict[str, Any]) -> str | None:
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list):
        return None
    for call in tool_calls:
        function = call.get("function") if isinstance(call, dict) else None
        arguments = function.get("arguments") if isinstance(function, dict) else None
        if isinstance(arguments, str) and arguments.strip():
            return arguments
    return None


def _safe_response_metadata(
    *,
    payload: dict[str, Any],
    choice: dict[str, Any],
    message: dict[str, Any],
    text: str,
    response_format: dict | None,
    max_output_tokens: int,
    usage_source: str,
    http_status: int | None,
    output_tokens: int | None,
    reasoning_tokens: int | None,
    content_source: str,
) -> dict[str, Any]:
    choices = payload.get("choices")
    tool_calls = message.get("tool_calls")
    return {
        "usage_source": usage_source,
        "http_status": http_status,
        "response_id": payload.get("id"),
        "generation_id": payload.get("id"),
        "finish_reason": choice.get("finish_reason"),
        "requested_max_tokens": max_output_tokens,
        "requested_response_format": response_format or {},
        "actual_output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "content_source": content_source,
        "content_length": len(text or ""),
        "response_shape": {
            "has_choices": isinstance(choices, list) and bool(choices),
            "choice_count": len(choices) if isinstance(choices, list) else 0,
            "has_message": bool(message),
            "has_message_content": bool(message.get("content")),
            "has_tool_calls": isinstance(tool_calls, list) and bool(tool_calls),
            "has_reasoning": bool(message.get("reasoning") or choice.get("reasoning")),
        },
    }
