from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.model_registry.defaults import MODELS, PRICING_SNAPSHOTS, PROVIDERS, SELECTION_RULES


class ModelRegistryStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = self.settings.project_path.parent / "model_registry"
        self.root.mkdir(parents=True, exist_ok=True)

    def ensure_defaults(self) -> None:
        self._ensure_models()
        self._ensure_json("providers.json", PROVIDERS)
        self._ensure_json("selection_rules.json", SELECTION_RULES)
        self._ensure_json("pricing_snapshots.json", PRICING_SNAPSHOTS)
        notes = self.root / "model_registry_notes.md"
        if not notes.exists():
            notes.write_text(
                "# Model Registry Notes\n\n"
                "- Registry pricing is for routing and safety estimates only.\n"
                "- Actual spend must come from provider responses, OpenRouter generation lookups, or official provider billing.\n"
                "- GPT-5.5 remains blocked by default for live use.\n"
                "- Vector memory v1 will later enhance context retrieval for model selection.\n",
                encoding="utf-8",
            )

    def read_json(self, name: str, fallback: Any) -> Any:
        self.ensure_defaults()
        path = self.root / name
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return fallback

    def read_notes(self) -> str:
        self.ensure_defaults()
        return (self.root / "model_registry_notes.md").read_text(encoding="utf-8")

    def _ensure_json(self, name: str, payload: Any) -> None:
        path = self.root / name
        if not path.exists():
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    def _ensure_models(self) -> None:
        path = self.root / "models.json"
        should_write = not path.exists()
        if not should_write:
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                should_write = len(existing) < 12 or any("approved_for_auto_selection" not in item for item in existing)
            except (OSError, json.JSONDecodeError, TypeError):
                should_write = True
        if should_write:
            path.write_text(json.dumps(MODELS, indent=2, ensure_ascii=True), encoding="utf-8")
