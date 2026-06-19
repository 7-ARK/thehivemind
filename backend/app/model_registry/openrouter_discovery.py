from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import Settings, get_settings


OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


class OpenRouterDiscoveryService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = self.settings.project_path.parent / "model_registry" / "provider_model_cache"
        self.root.mkdir(parents=True, exist_ok=True)
        self.cache_path = self.root / "openrouter_models.json"

    def read_cache(self) -> dict[str, Any]:
        if not self.cache_path.exists():
            return self._empty_cache()
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._empty_cache()
        payload.setdefault("provider", "openrouter")
        payload.setdefault("models", [])
        payload.setdefault("promoted_to_curated_registry", False)
        payload.setdefault("notes", [])
        return payload

    def summary(self) -> dict[str, Any]:
        cache = self.read_cache()
        models = cache.get("models", [])
        return {
            "provider": "openrouter",
            "cached_models_count": len(models),
            "last_synced_at": cache.get("last_synced_at"),
            "promoted_to_curated_registry": False,
            "sample_model_ids": [item.get("id") for item in models[:10] if isinstance(item, dict)],
            "notes": [
                "OpenRouter discovery is metadata-only.",
                "Discovered models are not automatically promoted to the curated registry.",
                "OpenRouter is not used as a search provider.",
            ],
        }

    async def sync(self) -> dict[str, Any]:
        headers = {}
        if self.settings.openrouter_api_key:
            headers["Authorization"] = f"Bearer {self.settings.openrouter_api_key}"
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(OPENROUTER_MODELS_URL, headers=headers)
            response.raise_for_status()
            payload = response.json()
        raw_models = payload.get("data", []) if isinstance(payload, dict) else []
        models = [_normalize_model(item) for item in raw_models if isinstance(item, dict)]
        cache = {
            "provider": "openrouter",
            "last_synced_at": datetime.now(UTC).isoformat(),
            "source": OPENROUTER_MODELS_URL,
            "promoted_to_curated_registry": False,
            "models": models,
            "notes": [
                "Discovery cache only; selector ignores these until a human promotes a curated model.",
                "No OpenRouter search provider is created from this data.",
            ],
        }
        self.cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=True), encoding="utf-8")
        return cache

    def _empty_cache(self) -> dict[str, Any]:
        return {
            "provider": "openrouter",
            "last_synced_at": None,
            "source": OPENROUTER_MODELS_URL,
            "promoted_to_curated_registry": False,
            "models": [],
            "notes": ["No OpenRouter discovery cache has been synced yet."],
        }


def _normalize_model(item: dict[str, Any]) -> dict[str, Any]:
    pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
    architecture = item.get("architecture") if isinstance(item.get("architecture"), dict) else {}
    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description"),
        "context_length": item.get("context_length"),
        "created": item.get("created"),
        "pricing": {
            "prompt": pricing.get("prompt"),
            "completion": pricing.get("completion"),
            "image": pricing.get("image"),
            "request": pricing.get("request"),
        },
        "architecture": {
            "modality": architecture.get("modality"),
            "tokenizer": architecture.get("tokenizer"),
            "instruct_type": architecture.get("instruct_type"),
        },
        "top_provider": item.get("top_provider"),
        "promoted_to_curated_registry": False,
    }
