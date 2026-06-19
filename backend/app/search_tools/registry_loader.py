from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.search_tools.defaults import SEARCH_PROVIDERS
from app.search_tools.schemas import SearchProviderEntry


class SearchRegistryLoader:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = self.settings.project_path.parent / "search_tools"
        self.root.mkdir(parents=True, exist_ok=True)

    def providers(self) -> list[SearchProviderEntry]:
        return [SearchProviderEntry.model_validate(item) for item in self._read_providers()]

    def get_provider(self, provider_id: str) -> SearchProviderEntry | None:
        for provider in self.providers():
            if provider.id == provider_id:
                return provider
        return None

    def status(self) -> dict[str, Any]:
        providers = [
            self._with_availability(provider, mode="live", allow_web_search=self.settings.allow_web_search)
            for provider in self.providers()
        ]
        return {
            "providers": [provider.model_dump() for provider in providers],
            "default_provider_id": self.settings.search_provider_default,
            "allow_web_search_global": self.settings.allow_web_search,
            "notes": [
                "Only Exa Direct API, OpenAI Web Search, and Gemini Google Search are registered.",
                "OpenRouter is intentionally excluded from search providers.",
            ],
        }

    def available_providers(self, *, mode: str, allow_web_search: bool, allow_gated: bool = False) -> list[SearchProviderEntry]:
        result = []
        for provider in self.providers():
            hydrated = self._with_availability(provider, mode=mode, allow_web_search=allow_web_search, allow_gated=allow_gated)
            if hydrated.available:
                result.append(hydrated)
        return result

    def _read_providers(self) -> list[dict[str, Any]]:
        path = self.root / "providers.json"
        if not path.exists():
            path.write_text(json.dumps(SEARCH_PROVIDERS, indent=2, ensure_ascii=True), encoding="utf-8")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = SEARCH_PROVIDERS
        ids = {item.get("id") for item in payload if isinstance(item, dict)}
        if ids != {"exa_direct", "openai_web_search", "gemini_google_search"} or _provider_defaults_stale(payload):
            payload = SEARCH_PROVIDERS
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return payload

    def _with_availability(
        self,
        provider: SearchProviderEntry,
        *,
        mode: str = "mock",
        allow_web_search: bool | None = None,
        allow_gated: bool = False,
    ) -> SearchProviderEntry:
        reasons = []
        allow_web_search = self.settings.allow_web_search if allow_web_search is None else allow_web_search
        configured = _provider_configured(self.settings, provider)
        enabled_by_setting = _provider_enabled_by_setting(self.settings, provider)
        base_active = provider.enabled and provider.status == "active"
        available_for_live = base_active and configured and enabled_by_setting
        live_search_available = available_for_live and (allow_web_search or not provider.requires_allow_web_search)
        mock_fixture_available = base_active and provider.available_in_mock
        if not configured:
            reasons.append(f"Missing one of: {', '.join(provider.env_keys_required)}.")
        if not enabled_by_setting:
            reasons.append("Provider-specific search feature flag is off.")
        if provider.requires_allow_web_search and not allow_web_search:
            reasons.append("ALLOW_WEB_SEARCH=false or this run did not enable allow_web_search.")
        if provider.requires_live_mode_for_real_search and mode != "live":
            reasons.append("Mock mode uses deterministic cached/search fixtures only.")
        if provider.blocked_by_default and not allow_gated:
            live_search_available = False
            reasons.append("Provider is gated and needs explicit approval.")
        if provider.provider == "openrouter":
            available_for_live = False
            live_search_available = False
            mock_fixture_available = False
            reasons.append("OpenRouter is not a supported search provider.")
        available = mock_fixture_available if mode != "live" else live_search_available
        return provider.model_copy(
            update={
                "configured": configured,
                "available": available,
                "available_for_live": available_for_live,
                "available_in_mock": mock_fixture_available,
                "allow_web_search_global": self.settings.allow_web_search,
                "live_search_available": live_search_available,
                "mock_fixture_available": mock_fixture_available,
                "reasons": reasons,
                "pricing_last_checked_at": provider.pricing_last_checked_at
                if provider.pricing_last_checked_at != "unknown"
                else datetime.now(UTC).date().isoformat(),
            }
        )


def _provider_configured(settings: Settings, provider: SearchProviderEntry) -> bool:
    if provider.provider == "exa":
        return bool(settings.exa_api_key)
    if provider.provider == "openai":
        return bool(settings.openai_api_key)
    if provider.provider == "gemini":
        return bool(settings.gemini_api_key or settings.google_api_key)
    return False


def _provider_enabled_by_setting(settings: Settings, provider: SearchProviderEntry) -> bool:
    if provider.provider == "exa":
        return settings.enable_exa_search
    if provider.provider == "openai":
        return settings.enable_openai_web_search
    if provider.provider == "gemini":
        return settings.enable_gemini_google_search or settings.enable_gemini_grounding
    return False


def _provider_defaults_stale(payload: list[dict[str, Any]]) -> bool:
    by_id = {item.get("id"): item for item in payload if isinstance(item, dict)}
    exa = by_id.get("exa_direct") or {}
    return (
        exa.get("base_cost_per_1000_requests") != 7.0
        or exa.get("pricing_source") != "manual_current_docs"
    )
