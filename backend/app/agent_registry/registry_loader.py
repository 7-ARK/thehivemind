from __future__ import annotations

import json
from typing import Any

from app.agent_registry.defaults import AGENT_RULES, AGENTS
from app.agent_registry.schemas import AgentRegistryEntry
from app.core.config import Settings, get_settings


class AgentRegistryLoader:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = self.settings.project_path.parent / "agent_registry"
        self.root.mkdir(parents=True, exist_ok=True)

    def agents(self) -> list[AgentRegistryEntry]:
        self.ensure_defaults()
        return [AgentRegistryEntry.model_validate(item) for item in self._read_json("agents.json", AGENTS)]

    def rules(self) -> dict[str, Any]:
        self.ensure_defaults()
        return self._read_json("agent_rules.json", AGENT_RULES)

    def get_agent(self, agent_id: str) -> AgentRegistryEntry | None:
        normalized = agent_id.lower()
        return next((agent for agent in self.agents() if agent.id.lower() == normalized), None)

    def ensure_defaults(self) -> None:
        self._ensure_agents()
        self._ensure_rules()

    def _read_json(self, name: str, fallback: Any) -> Any:
        path = self.root / name
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return fallback

    def _ensure_json(self, name: str, payload: Any) -> None:
        path = self.root / name
        if not path.exists():
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")

    def _ensure_agents(self) -> None:
        path = self.root / "agents.json"
        if not path.exists():
            path.write_text(json.dumps(AGENTS, indent=2, ensure_ascii=True), encoding="utf-8")
            return
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            path.write_text(json.dumps(AGENTS, indent=2, ensure_ascii=True), encoding="utf-8")
            return
        if not isinstance(existing, list):
            return
        existing_ids = {item.get("id") for item in existing if isinstance(item, dict)}
        missing = [agent for agent in AGENTS if agent.get("id") not in existing_ids]
        if missing:
            path.write_text(json.dumps([*existing, *missing], indent=2, ensure_ascii=True), encoding="utf-8")

    def _ensure_rules(self) -> None:
        path = self.root / "agent_rules.json"
        if not path.exists():
            path.write_text(json.dumps(AGENT_RULES, indent=2, ensure_ascii=True), encoding="utf-8")
            return
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            path.write_text(json.dumps(AGENT_RULES, indent=2, ensure_ascii=True), encoding="utf-8")
            return
        if not isinstance(existing, dict):
            return
        changed = False
        for section, defaults in AGENT_RULES.items():
            if section not in existing:
                existing[section] = defaults
                changed = True
            elif isinstance(defaults, dict) and isinstance(existing[section], dict):
                for key, value in defaults.items():
                    if key not in existing[section]:
                        existing[section][key] = value
                        changed = True
        if changed:
            path.write_text(json.dumps(existing, indent=2, ensure_ascii=True), encoding="utf-8")
