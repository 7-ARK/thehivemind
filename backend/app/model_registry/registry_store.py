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
        if not path.exists():
            path.write_text(json.dumps(MODELS, indent=2, ensure_ascii=True), encoding="utf-8")
            return

        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            path.write_text(json.dumps(MODELS, indent=2, ensure_ascii=True), encoding="utf-8")
            return
        if not isinstance(existing, list):
            path.write_text(json.dumps(MODELS, indent=2, ensure_ascii=True), encoding="utf-8")
            return

        defaults_by_id = {item.get("id"): item for item in MODELS if isinstance(item, dict) and item.get("id")}
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        changed = False
        for item in existing:
            if not isinstance(item, dict):
                changed = True
                continue
            model_id = item.get("id")
            default = defaults_by_id.get(model_id)
            if default:
                merged_item = {**default, **item}
                if merged_item != item:
                    changed = True
                merged.append(merged_item)
                seen.add(model_id)
            else:
                merged.append(item)

        for model_id, item in defaults_by_id.items():
            if model_id not in seen:
                merged.append(item)
                changed = True

        if changed:
            path.write_text(json.dumps(merged, indent=2, ensure_ascii=True), encoding="utf-8")
