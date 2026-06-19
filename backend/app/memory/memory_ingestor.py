from __future__ import annotations

import json
from typing import Any

from app.artifacts.artifact_store import ArtifactStore
from app.core.config import Settings, get_settings
from app.core.models import RunRecord
from app.memory.memory_policies import active_constraints_from_command
from app.memory.memory_store import MemoryStore
from app.memory.memory_summarizer import compact_text, extract_warnings, source_summary, summarize_json
from app.orchestration.run_manager import RunManager


class MemoryIngestor:
    def __init__(self, settings: Settings | None = None, store: MemoryStore | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = store or MemoryStore(self.settings)
        self.artifacts = ArtifactStore(self.settings)

    def ingest_run(self, run_id: str) -> dict[str, Any]:
        run = RunManager(self.settings).get_run(run_id)
        if run is None:
            return {"run_id": run_id, "inserted": 0, "reason": "run not found"}
        return self.ingest_record(run)

    def ingest_record(self, run: RunRecord) -> dict[str, Any]:
        if not self.settings.memory_ingest_after_run:
            return {"run_id": run.run_id, "inserted": 0, "reason": "memory ingestion disabled"}
        inserted = []
        project_id = run.project_id or "unassigned"
        base_tags = [project_id, run.run_type, run.mode]
        final_summary = compact_text(run.final_output.summary)
        inserted.append(
            self.store.add_item(
                {
                    "project_id": project_id,
                    "memory_type": "run_summary",
                    "title": f"Run summary {run.run_id[:8]}",
                    "summary": final_summary,
                    "content": "\n".join([final_summary, *run.final_output.what_was_done, *run.final_output.recommended_next_actions]),
                    "source_type": "run",
                    "source_run_id": run.run_id,
                    "tags": [*base_tags, "run_summary"],
                    "importance": 3,
                    "models_used": run.models_used,
                    "agents_used": [agent.name for agent in run.agents],
                }
            ).id
        )
        for artifact in run.artifacts or self.artifacts.list_artifacts(run.run_id):
            content = self._artifact_content(run.run_id, artifact.id)
            if not content:
                continue
            if artifact.name == "agent_plan.json":
                inserted.append(self._add_json_memory(project_id, run, artifact, content, "agent_plan", "agent_plan", ["planner", "constraints"]))
            elif artifact.name == "model_selection.json":
                inserted.append(self._add_json_memory(project_id, run, artifact, content, "model_selection", "model_selection", ["models", "routing"]))
            elif artifact.name == "research_brief.md":
                inserted.append(
                    self.store.add_item(
                        {
                            "project_id": project_id,
                            "memory_type": "research_brief",
                            "title": f"Research brief {run.run_id[:8]}",
                            "summary": compact_text(content, 700),
                            "content": compact_text(content, 1200),
                            "source_type": "artifact",
                            "source_path": artifact.name,
                            "source_run_id": run.run_id,
                            "source_artifact_id": artifact.id,
                            "tags": [*base_tags, "research"],
                            "importance": 4,
                            "allowed_agents": ["research_agent", "website_agent", "qa_agent"],
                        }
                    ).id
                )
            elif artifact.name == "research_sources.json":
                try:
                    payload = json.loads(content)
                except json.JSONDecodeError:
                    payload = {}
                summary, urls = source_summary(payload)
                inserted.append(
                    self.store.add_item(
                        {
                            "project_id": project_id,
                            "memory_type": "research_source_summary",
                            "title": f"Research sources {run.run_id[:8]}",
                            "summary": summary,
                            "content": summarize_json(payload, 1200),
                            "source_type": "search_source",
                            "source_path": artifact.name,
                            "source_run_id": run.run_id,
                            "source_artifact_id": artifact.id,
                            "tags": [*base_tags, "sources", str(payload.get("provider_id") or "")],
                            "importance": 4,
                            "allowed_agents": ["research_agent", "website_agent", "qa_agent"],
                            "search_provider": payload.get("provider_id"),
                            "source_urls": urls,
                            "metadata": {"mock_fixture": payload.get("mock_fixture"), "source_count": payload.get("source_count")},
                        }
                    ).id
                )
            elif artifact.name == "qa_review.md":
                warnings = extract_warnings(content)
                inserted.append(
                    self.store.add_item(
                        {
                            "project_id": project_id,
                            "memory_type": "qa_warning",
                            "title": f"QA warnings {run.run_id[:8]}",
                            "summary": "; ".join(warnings) or compact_text(content, 500),
                            "content": compact_text(content, 1000),
                            "source_type": "qa_review",
                            "source_path": artifact.name,
                            "source_run_id": run.run_id,
                            "source_artifact_id": artifact.id,
                            "tags": [*base_tags, "qa", "warnings"],
                            "importance": 4,
                            "allowed_agents": ["qa_agent", "website_agent", "research_agent"],
                        }
                    ).id
                )
        constraints = active_constraints_from_command(run.command, run.run_type)
        if constraints:
            inserted.append(
                self.store.add_item(
                    {
                        "project_id": project_id,
                        "memory_type": "safety_constraint",
                        "title": f"Constraints from {run.run_id[:8]}",
                        "summary": "; ".join(constraints),
                        "content": "\n".join(constraints),
                        "source_type": "run",
                        "source_run_id": run.run_id,
                        "tags": [*base_tags, "constraints"],
                        "importance": 5,
                    }
                ).id
            )
        file_paths = [*run.project_files_created, *run.project_files_updated]
        if file_paths:
            inserted.append(
                self.store.add_item(
                    {
                        "project_id": project_id,
                        "memory_type": "file_change_summary",
                        "title": f"File changes {run.run_id[:8]}",
                        "summary": f"Changed {len(file_paths)} project file(s): {', '.join(file_paths[:10])}",
                        "content": "\n".join(file_paths),
                        "source_type": "run",
                        "source_run_id": run.run_id,
                        "tags": [*base_tags, "files"],
                        "importance": 3,
                        "file_paths": file_paths,
                        "allowed_agents": ["website_agent", "qa_agent"],
                    }
                ).id
            )
        for command in run.commands_run:
            if command.get("exit_code") not in (None, 0) or command.get("error_type"):
                inserted.append(
                    self.store.add_item(
                        {
                            "project_id": project_id,
                            "memory_type": "command_result",
                            "title": f"Command result {run.run_id[:8]}",
                            "summary": f"{command.get('command')} exited {command.get('exit_code')}: {command.get('error_message') or command.get('stderr') or ''}",
                            "content": summarize_json(command, 900),
                            "source_type": "command_log",
                            "source_run_id": run.run_id,
                            "tags": [*base_tags, "command"],
                            "importance": 4,
                            "error_types": [str(command.get("error_type"))] if command.get("error_type") else [],
                        }
                    ).id
                )
        if run.final_output.recommended_next_actions:
            inserted.append(
                self.store.add_item(
                    {
                        "project_id": project_id,
                        "memory_type": "next_step",
                        "title": f"Next step {run.run_id[:8]}",
                        "summary": run.final_output.recommended_next_actions[0],
                        "content": "\n".join(run.final_output.recommended_next_actions),
                        "source_type": "run",
                        "source_run_id": run.run_id,
                        "tags": [*base_tags, "next_step"],
                        "importance": 3,
                    }
                ).id
            )
        self.store.rebuild_index(project_id)
        return {"run_id": run.run_id, "project_id": project_id, "inserted": len(inserted), "memory_ids": inserted}

    def _artifact_content(self, run_id: str, artifact_id: str) -> str:
        try:
            return self.artifacts.get_artifact(run_id, artifact_id).content
        except Exception:
            return ""

    def _add_json_memory(self, project_id: str, run: RunRecord, artifact: Any, content: str, memory_type: str, title: str, tags: list[str]) -> str:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            payload = content
        return self.store.add_item(
            {
                "project_id": project_id,
                "memory_type": memory_type,
                "title": f"{title} {run.run_id[:8]}",
                "summary": summarize_json(payload, 700),
                "content": summarize_json(payload, 1200),
                "source_type": "model_selection" if memory_type == "model_selection" else "artifact",
                "source_path": artifact.name,
                "source_run_id": run.run_id,
                "source_artifact_id": artifact.id,
                "tags": [project_id, run.run_type, *tags],
                "importance": 4 if memory_type == "agent_plan" else 3,
                "allowed_agents": ["model_selector_agent", "qa_agent", "research_agent", "website_agent"],
            }
        ).id
