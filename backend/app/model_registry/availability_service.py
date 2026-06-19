from __future__ import annotations

from app.core.config import Settings, get_settings
from app.model_registry.registry_loader import ModelRegistryLoader
from app.model_registry.schemas import ModelAvailability, ModelRegistryEntry


class ModelAvailabilityService:
    def __init__(self, settings: Settings | None = None, loader: ModelRegistryLoader | None = None) -> None:
        self.settings = settings or get_settings()
        self.loader = loader or ModelRegistryLoader(self.settings)

    def all(self, *, mode: str = "mock", search_required: bool = False) -> list[ModelAvailability]:
        return [self.availability(model, mode=mode, search_required=search_required) for model in self.loader.models()]

    def availability(self, model: ModelRegistryEntry, *, mode: str = "mock", search_required: bool = False) -> ModelAvailability:
        reasons: list[str] = []
        configured = self._provider_configured(model.provider)
        search_enabled = self._search_enabled(model.provider)
        available = True

        if not model.enabled or model.status == "disabled":
            available = False
            reasons.append("Model is disabled in registry.")
        if model.status == "planned" or model.curated_tier == "planned":
            available = False
            reasons.append("Model is planned/discovery-only and not promoted for selection.")
        if not model.approved_for_auto_selection or not model.auto_selectable:
            reasons.append("Model is not approved for automatic selection.")
        if mode == "live":
            if not model.available_for_live or not model.allowed_in_live:
                available = False
                reasons.append("Model is not allowed for live mode.")
            if not self.settings.is_live_allowed():
                available = False
                reasons.append("Live provider calls are disabled by backend settings.")
            if not configured:
                available = False
                reasons.append(f"{model.provider} API key is not configured.")
        elif not model.allowed_in_mock:
            available = False
            reasons.append("Model is not allowed in mock mode.")

        if search_required and not (model.supports_web_search and search_enabled):
            available = False
            reasons.append("Search was required, but this model/provider search path is unavailable.")

        return ModelAvailability(
            model_id=model.id,
            provider=model.provider,
            available=available,
            available_for_live=model.available_for_live,
            provider_configured=configured,
            search_enabled=search_enabled,
            blocked_by_default=model.blocked_by_default,
            requires_approval=model.requires_approval or model.requires_human_approval_for_live or model.requires_human_approval_for_high_cost,
            auto_selectable=available and not model.blocked_by_default and not model.requires_approval and getattr(model, "approved_for_auto_selection", True),
            selectable_in_mock=model.enabled and model.allowed_in_mock and not model.blocked_by_default,
            selectable_in_live_without_approval=(
                model.enabled
                and model.allowed_in_live
                and model.available_for_live
                and configured
                and self.settings.is_live_allowed()
                and not model.blocked_by_default
                and not model.requires_approval
                and not model.requires_human_approval_for_live
            ),
            reasons=reasons,
        )

    def _provider_configured(self, provider: str) -> bool:
        try:
            return bool(self.settings.get_provider_key(provider))
        except Exception:
            return False

    def _search_enabled(self, provider: str) -> bool:
        normalized = provider.lower()
        if normalized == "openai":
            return self.settings.enable_openai_web_search
        if normalized == "gemini":
            return self.settings.enable_gemini_grounding
        if normalized == "openrouter":
            return self.settings.enable_openrouter_search
        return False
