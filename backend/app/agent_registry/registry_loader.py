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
        self._ensure_json("agents.json", AGENTS)
        self._ensure_json("agent_rules.json", AGENT_RULES)

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

