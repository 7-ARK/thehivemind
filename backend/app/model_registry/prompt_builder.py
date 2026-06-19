from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.model_registry.registry_loader import ModelRegistryLoader
from app.projects.project_workspace import ProjectWorkspaceManager


class SelectorPromptBuilder:
    def __init__(self, settings: Settings | None = None, loader: ModelRegistryLoader | None = None) -> None:
        self.settings = settings or get_settings()
        self.loader = loader or ModelRegistryLoader(self.settings)

    def context_packet(self, *, command: str, project_id: str | None = None) -> dict[str, Any]:
        project_summary = ""
        current_files: list[str] = []
        warnings: list[str] = []
        if project_id:
            manager = ProjectWorkspaceManager(self.settings)
            try:
                manager.ensure_project_workspace(project_id)
                project_summary = manager.read_project_file(project_id, "project_state.md")[:1200]
                current_files = [item.path for item in manager.get_project_manifest(project_id).files[:30]]
            except Exception as exc:
                warnings.append(f"Project context unavailable: {exc}")

        return {
            "project_summary": project_summary,
            "recent_run_summary": self._latest_artifact_summary(project_id),
            "user_constraints": extract_user_constraints(command),
            "known_preferences": self._known_preferences(command),
            "current_files": current_files,
            "warnings_from_previous_runs": warnings,
            "registry_notes": self.loader.notes()[:800],
            "todo": "Vector memory v1 will later replace or enhance this compact context retrieval.",
        }

    def compact_prompt(self, *, task_summary: str, constraints: dict[str, Any], candidates: list[dict[str, Any]], context_packet: dict[str, Any]) -> str:
        return json.dumps(
            {
                "task_summary": task_summary,
                "constraints": constraints,
                "candidate_summaries": candidates,
                "context_packet": context_packet,
                "output_schema": {
                    "selected_model_id": "...",
                    "provider": "...",
                    "reason": "...",
                    "confidence": 0.0,
                    "estimated_risk": "low|medium|high",
                    "requires_approval": False,
                    "fallback_model_id": "...",
                    "why_not_others": [{"model_id": "...", "reason": "..."}],
                    "cost_guard": {"within_budget": True, "max_allowed_cost": 0.01},
                },
            },
            indent=2,
        )

    def _latest_artifact_summary(self, project_id: str | None) -> str:
        if not project_id:
            return ""
        project_root = self.settings.project_path / project_id
        history = project_root / "logs" / "project_history.json"
        if not history.exists():
            return ""
        try:
            return Path(history).read_text(encoding="utf-8")[-1200:]
        except OSError:
            return ""

    def _known_preferences(self, command: str) -> list[str]:
        lowered = command.lower()
        preferences = []
        if any(phrase in lowered for phrase in ("cheap", "low cost", "save cost")):
            preferences.append("Prefer low-cost worker models.")
        if "do not use gpt-5.5" in lowered or "no gpt-5.5" in lowered:
            preferences.append("Exclude GPT-5.5 family models.")
        return preferences


def extract_user_constraints(command: str) -> list[str]:
    lowered = command.lower()
    constraints = []
    patterns = {
        "deploy": ["do not deploy", "don't deploy", "no deploy", "no deployment"],
        "package_install": ["do not install packages", "don't install packages", "no package installs", "do not install dependencies"],
        "external_actions": ["no external actions", "do not use external actions", "don't use external actions"],
        "email": ["do not send emails", "don't send emails", "no emails"],
        "social_posting": ["do not post", "don't post", "no social posting"],
        "gpt-5.5": ["do not use gpt-5.5", "don't use gpt-5.5", "no gpt-5.5"],
        "file_writes": ["do not create files", "do not write files", "no file writes"],
        "commands": ["do not run commands", "do not execute commands", "no commands"],
    }
    for label, phrases in patterns.items():
        if any(phrase in lowered for phrase in phrases):
            constraints.append(label)
    return constraints

