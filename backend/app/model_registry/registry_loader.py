from __future__ import annotations

from app.core.config import Settings
from app.model_registry.defaults import MODELS, PROVIDERS, SELECTION_RULES
from app.model_registry.registry_store import ModelRegistryStore
from app.model_registry.schemas import ModelRegistryEntry, ProviderRegistryEntry


class ModelRegistryLoader:
    def __init__(self, settings: Settings | None = None) -> None:
        self.store = ModelRegistryStore(settings)

    def models(self) -> list[ModelRegistryEntry]:
        return [ModelRegistryEntry.model_validate(item) for item in self.store.read_json("models.json", MODELS)]

    def providers(self) -> list[ProviderRegistryEntry]:
        return [ProviderRegistryEntry.model_validate(item) for item in self.store.read_json("providers.json", PROVIDERS)]

    def rules(self) -> dict:
        return self.store.read_json("selection_rules.json", SELECTION_RULES)

    def notes(self) -> str:
        return self.store.read_notes()

    def get_model(self, model_id: str) -> ModelRegistryEntry | None:
        normalized = model_id.lower()
        return next((model for model in self.models() if model.id.lower() == normalized), None)

    def compact_summary(self, model: ModelRegistryEntry) -> dict:
        return {
            "id": model.id,
            "provider": model.provider,
            "status": model.status,
            "enabled": model.enabled,
            "cost_level": model.cost_level,
            "quality_level": model.quality_level,
            "tags": model.selection_tags[:8],
            "supports": {
                "search": model.supports_web_search,
                "tools": model.supports_tool_use,
                "json": model.supports_json,
                "vision": model.supports_vision,
                "structured_output": model.supports_structured_output,
            },
            "recommended_cost_per_call": model.max_cost_per_call_recommended,
            "requires_approval": model.requires_approval or model.requires_human_approval_for_live,
            "best_for": model.best_for[:3],
        }

