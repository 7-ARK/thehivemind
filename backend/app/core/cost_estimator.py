from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    input_per_million: float
    output_per_million: float


MODEL_PRICING_USD: dict[str, ModelPrice] = {
    # Approximate planning numbers for MVP demos, not billing guarantees.
    "gpt-5.5": ModelPrice(input_per_million=3.0, output_per_million=12.0),
    "gemini-3.5-flash": ModelPrice(input_per_million=0.35, output_per_million=1.05),
    "gpt-5.4-nano": ModelPrice(input_per_million=0.08, output_per_million=0.32),
    "gemini-3.1-flash-lite": ModelPrice(input_per_million=0.05, output_per_million=0.20),
}


def estimate_tokens(text: str) -> int:
    """Small, transparent estimator: roughly four characters per token."""

    return max(1, len(text) // 4)


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price = MODEL_PRICING_USD.get(model, ModelPrice(0.10, 0.40))
    input_cost = (input_tokens / 1_000_000) * price.input_per_million
    output_cost = (output_tokens / 1_000_000) * price.output_per_million
    return round(input_cost + output_cost, 6)

