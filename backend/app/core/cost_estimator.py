from fastapi import HTTPException
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.model_registry import get_model_metadata


class CostEstimate(BaseModel):
    model: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    estimated_cost_usd: float


def estimate_tokens(text: str) -> int:
    """Small, transparent estimator: roughly four characters per token."""

    return max(1, len(text) // 4)


def estimate_messages_tokens(messages: list[dict]) -> int:
    text = "\n".join(str(message.get("content", "")) for message in messages)
    # Add a tiny overhead per message so short chat payloads are not undercounted.
    return estimate_tokens(text) + (len(messages) * 4)


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int = 0,
    service_tier: str | None = None,
) -> CostEstimate:
    metadata = get_model_metadata(model, service_tier)
    billable_input_tokens = max(0, input_tokens - cached_input_tokens)
    cached_price = metadata.cached_input_price_per_1m
    input_cost = (billable_input_tokens / 1_000_000) * metadata.input_price_per_1m
    cached_cost = 0.0
    if cached_input_tokens and cached_price is not None:
        cached_cost = (cached_input_tokens / 1_000_000) * cached_price
    elif cached_input_tokens:
        cached_cost = (cached_input_tokens / 1_000_000) * metadata.input_price_per_1m
    output_cost = (output_tokens / 1_000_000) * metadata.output_price_per_1m
    return CostEstimate(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
        estimated_cost_usd=round(input_cost + cached_cost + output_cost, 6),
    )


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    return estimate_cost(model, input_tokens, output_tokens).estimated_cost_usd


def assert_call_budget(
    model: str,
    input_tokens: int,
    output_tokens: int,
    service_tier: str | None = None,
    max_output_tokens_per_call: int | None = None,
) -> CostEstimate:
    settings = get_settings()
    output_limit = max_output_tokens_per_call or settings.max_output_tokens_per_call
    if input_tokens > settings.max_input_tokens_per_call:
        raise HTTPException(
            status_code=400,
            detail=f"Input token estimate {input_tokens} exceeds MAX_INPUT_TOKENS_PER_CALL={settings.max_input_tokens_per_call}.",
        )
    if output_tokens > output_limit:
        label = "MAX_OUTPUT_TOKENS_PER_CALL" if max_output_tokens_per_call is None else "configured output token limit"
        raise HTTPException(
            status_code=400,
            detail=f"Requested output tokens {output_tokens} exceeds {label}={output_limit}.",
        )
    estimate = estimate_cost(model, input_tokens, output_tokens, service_tier=service_tier)
    if estimate.estimated_cost_usd > settings.max_cost_per_call_usd:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Estimated call cost ${estimate.estimated_cost_usd:.6f} exceeds "
                f"MAX_COST_PER_CALL_USD=${settings.max_cost_per_call_usd:.2f}."
            ),
        )
    return estimate


def assert_run_budget(estimated_total_cost_usd: float) -> None:
    settings = get_settings()
    if estimated_total_cost_usd > settings.max_cost_per_run_usd:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Estimated run cost ${estimated_total_cost_usd:.6f} exceeds "
                f"MAX_COST_PER_RUN_USD=${settings.max_cost_per_run_usd:.2f}."
            ),
        )
