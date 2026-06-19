from __future__ import annotations

from app.model_registry.schemas import ModelRegistryEntry


class ModelPricingService:
    def estimated_call_cost(self, model: ModelRegistryEntry, *, input_tokens: int = 1000, output_tokens: int = 300) -> float:
        input_cost = (model.input_cost_per_1m_tokens or 0) * input_tokens / 1_000_000
        output_cost = (model.output_cost_per_1m_tokens or 0) * output_tokens / 1_000_000
        return round(input_cost + output_cost, 6)

    def within_budget(self, model: ModelRegistryEntry, max_cost_usd: float) -> bool:
        return model.max_cost_per_call_recommended <= max_cost_usd

