from __future__ import annotations

from app.core.config import Settings, get_settings
from app.search_tools.registry_loader import SearchRegistryLoader
from app.search_tools.schemas import SearchSelectionRequest, SearchSelectionResult


class SearchSelector:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.loader = SearchRegistryLoader(self.settings)

    def select(self, request: SearchSelectionRequest) -> SearchSelectionResult:
        search_needed = _search_needed(request.query)
        if not search_needed:
            return SearchSelectionResult(search_needed=False, reason="Task does not require web search.")
        if not request.allow_web_search:
            return SearchSelectionResult(
                search_needed=True,
                search_unavailable=True,
                reason="Search is disabled for this run because allow_web_search is false.",
            )

        if request.explicit_provider_id:
            provider = self.loader.get_provider(request.explicit_provider_id)
            if provider is None:
                return SearchSelectionResult(search_needed=True, search_unavailable=True, reason="Requested search provider is not registered.")
            hydrated = self.loader._with_availability(provider, mode=request.mode, allow_web_search=request.allow_web_search, allow_gated=request.allow_gated)
            if not hydrated.available:
                return SearchSelectionResult(
                    search_needed=True,
                    selected_provider_id=hydrated.id,
                    search_unavailable=True,
                    reason="Requested provider unavailable: " + "; ".join(hydrated.reasons),
                )
            return SearchSelectionResult(search_needed=True, selected_provider_id=hydrated.id, provider_ids=[hydrated.id], reason="Explicit search provider selected.")

        providers = self.loader.available_providers(mode=request.mode, allow_web_search=request.allow_web_search, allow_gated=request.allow_gated)
        if not providers:
            return SearchSelectionResult(search_needed=True, search_unavailable=True, reason="No configured search providers are available for this run.")

        default_id = self.settings.search_provider_default
        selected = next((provider for provider in providers if provider.id == default_id), providers[0])
        if request.combined_search:
            provider_ids = [provider.id for provider in providers[:2]]
            return SearchSelectionResult(
                search_needed=True,
                selected_provider_id=selected.id,
                combined_search_used=len(provider_ids) > 1,
                provider_ids=provider_ids,
                reason="Combined search requested; selected available providers in priority order.",
            )
        return SearchSelectionResult(search_needed=True, selected_provider_id=selected.id, provider_ids=[selected.id], reason="Best available search provider selected.")


def _search_needed(query: str) -> bool:
    lowered = _strip_negated_search_phrases(query.lower())
    return any(
        phrase in lowered
        for phrase in (
            "research",
            "competitor",
            "latest",
            "current",
            "web search",
            "browse",
            "find sources",
            "market trends",
            "sources",
        )
    )


def _strip_negated_search_phrases(query: str) -> str:
    for phrase in (
        "do not run live web search",
        "don't run live web search",
        "do not use live web search",
        "don't use live web search",
        "do not run web search",
        "don't run web search",
        "do not web search",
        "don't web search",
        "do not search",
        "don't search",
        "no live web search",
        "no web search",
        "without live web search",
        "without web search",
        "do not browse",
        "don't browse",
        "no browsing",
        "without browsing",
    ):
        query = query.replace(phrase, "")
    return query
