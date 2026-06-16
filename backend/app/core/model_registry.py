from pydantic import BaseModel


class ModelMetadata(BaseModel):
    model_name: str
    provider: str
    role: str
    input_price_per_1m: float
    cached_input_price_per_1m: float | None = None
    output_price_per_1m: float
    supports_search: bool = False
    supports_vision: bool = False
    notes: str = ""


MODEL_REGISTRY: dict[str, ModelMetadata] = {
    "gpt-5.5": ModelMetadata(
        model_name="gpt-5.5",
        provider="openai",
        role="CEO / master planner",
        input_price_per_1m=5.00,
        cached_input_price_per_1m=0.50,
        output_price_per_1m=30.00,
        supports_search=False,
        supports_vision=True,
        notes="Standard tier planning model. Not called automatically in this backend step.",
    ),
    "gpt-5.5:flex": ModelMetadata(
        model_name="gpt-5.5",
        provider="openai",
        role="CEO / master planner flex tier",
        input_price_per_1m=2.50,
        cached_input_price_per_1m=0.25,
        output_price_per_1m=15.00,
        supports_search=False,
        supports_vision=True,
        notes="Flex pricing assumption for CEO planning. Guarded from automatic calls.",
    ),
    "gpt-5.4-nano": ModelMetadata(
        model_name="gpt-5.4-nano",
        provider="openai",
        role="cheap non-search worker / provider testing",
        input_price_per_1m=0.20,
        cached_input_price_per_1m=0.02,
        output_price_per_1m=1.25,
        supports_search=False,
        supports_vision=False,
        notes="Preferred OpenAI model for safe low-cost provider tests.",
    ),
    "gemini-3.5-flash": ModelMetadata(
        model_name="gemini-3.5-flash",
        provider="gemini",
        role="model selector / fast routing",
        input_price_per_1m=1.50,
        output_price_per_1m=9.00,
        supports_search=False,
        supports_vision=True,
        notes="Search/grounding remains disabled for now.",
    ),
    "gemini-3.1-flash-lite": ModelMetadata(
        model_name="gemini-3.1-flash-lite",
        provider="gemini",
        role="cheap search/multimodal worker placeholder",
        input_price_per_1m=0.25,
        output_price_per_1m=1.50,
        supports_search=False,
        supports_vision=True,
        notes="Preferred Gemini model for safe low-cost provider tests. Grounding is disabled.",
    ),
    "qwen/qwen3-coder": ModelMetadata(
        model_name="qwen/qwen3-coder",
        provider="openrouter",
        role="OpenRouter cheap coding worker placeholder",
        input_price_per_1m=0.10,
        output_price_per_1m=0.40,
        supports_search=False,
        supports_vision=False,
        notes="Placeholder assumption until OpenRouter model-specific pricing is wired in.",
    ),
}


def get_model_metadata(model: str, service_tier: str | None = None) -> ModelMetadata:
    if model == "gpt-5.5" and service_tier == "flex":
        return MODEL_REGISTRY["gpt-5.5:flex"]
    if model in MODEL_REGISTRY:
        return MODEL_REGISTRY[model]
    return ModelMetadata(
        model_name=model,
        provider="unknown",
        role="unregistered model",
        input_price_per_1m=0.10,
        output_price_per_1m=0.40,
        supports_search=False,
        supports_vision=False,
        notes="Fallback pricing for unregistered model. Add this model to MODEL_REGISTRY before production use.",
    )


def models_for_provider(provider: str) -> list[ModelMetadata]:
    return [model for model in MODEL_REGISTRY.values() if model.provider == provider]
