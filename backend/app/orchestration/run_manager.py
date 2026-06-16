import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.agents.base_agent import BaseAgent
from app.agents.ceo_agent import CEOAgent
from app.agents.coding_agent import CodingAgent
from app.agents.content_agent import ContentAgent
from app.agents.model_selector_agent import ModelSelectorAgent
from app.agents.qa_agent import QAAgent
from app.agents.research_agent import ResearchAgent
from app.core.config import Settings, get_settings
from app.core.model_registry import get_model_metadata
from app.core.models import AgentInfo, FinalOutput, RunMetrics, RunRecord
from app.memory.current_state import update_current_state
from app.memory.retrieval import retrieve_memory
from app.orchestration.event_stream import build_event
from app.orchestration.task_graph import build_default_task_graph
from app.storage.usage_store import UsageStore


class RunManager:
    """Coordinates the visible MVP workflow and persists run records to SQLite."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.db_path = self.settings.sqlite_path
        self._ensure_database()

    def start_run(self, command: str, mode: str = "mock") -> RunRecord:
        if mode != "mock" or self.settings.mock_mode:
            mode = "mock"

        run_id = str(uuid.uuid4())
        started_at = datetime.now(UTC)
        memory = retrieve_memory(command)
        agents = self._build_agents()

        ceo_plan = agents["ceo"].build_plan(command)
        agents["ceo"].mark_complete("Created execution plan", ceo_plan)

        routing = agents["selector"].route_models()
        agents["selector"].mark_complete("Selected models by task type", routing)

        research_output = agents["research"].research(command)
        agents["research"].mark_complete("Produced research brief", research_output)

        coding_output = agents["coding"].produce_task(command)
        agents["coding"].mark_complete("Produced technical task list", coding_output)

        content_output = agents["content"].draft(command)
        agents["content"].mark_complete("Drafted content deliverables", content_output)

        qa_output = agents["qa"].review()
        agents["qa"].mark_complete("Reviewed final package", qa_output)

        events = [
            build_event(
                agent_name=agents["ceo"].name,
                agent_role=agents["ceo"].role,
                action_summary="Received command and created a practical execution plan.",
                input_summary=command,
                output_summary=ceo_plan,
                model_used=self.settings.ceo_model,
            ),
            build_event(
                agent_name=agents["selector"].name,
                agent_role=agents["selector"].role,
                action_summary="Matched each task to the cheapest useful model tier.",
                input_summary=ceo_plan,
                output_summary=routing,
                model_used=self.settings.model_selector_model,
            ),
            build_event(
                agent_name=agents["research"].name,
                agent_role=agents["research"].role,
                action_summary="Created a research task and returned a concise brief.",
                input_summary=f"{command}\nMemory: {memory.retrieved_snippets[0].content}",
                output_summary=research_output,
                model_used=self.settings.cheap_search_worker_model,
            ),
            build_event(
                agent_name=agents["coding"].name,
                agent_role=agents["coding"].role,
                action_summary="Mapped the plan into technical systems and automations.",
                input_summary=ceo_plan,
                output_summary=coding_output,
                model_used=self.settings.cheap_worker_model,
            ),
            build_event(
                agent_name=agents["content"].name,
                agent_role=agents["content"].role,
                action_summary="Turned agent findings into user-facing messaging and deliverables.",
                input_summary=f"{research_output}\n{coding_output}",
                output_summary=content_output,
                model_used=self.settings.cheap_worker_model,
            ),
            build_event(
                agent_name=agents["qa"].name,
                agent_role=agents["qa"].role,
                action_summary="Reviewed the package and prepared final output.",
                input_summary=f"{research_output}\n{coding_output}\n{content_output}",
                output_summary=qa_output,
                model_used=self.settings.cheap_worker_model,
            ),
            build_event(
                agent_name="TheHiveMind",
                agent_role="Final assembly",
                action_summary="Compiled the reviewed work into a final answer.",
                input_summary=qa_output,
                output_summary="Final report assembled with next actions and generated task artifacts.",
                model_used=self.settings.ceo_model,
            ),
        ]

        completed_at = datetime.now(UTC)
        metrics = self._build_metrics(events, started_at, completed_at, len(memory.retrieved_snippets))
        final_output = self._build_final_output(command)
        record = RunRecord(
            run_id=run_id,
            command=command,
            mode=mode,
            status="completed",
            started_at=started_at,
            completed_at=completed_at,
            events=events,
            agents=[self._agent_info(agent) for agent in agents.values()],
            task_graph=build_default_task_graph(),
            metrics=metrics,
            memory=memory,
            final_output=final_output,
        )

        update_current_state(f"Last completed run: {command}. Status: completed. Run ID: {run_id}.")
        self._save_run(record)
        self._log_usage_for_events(record)
        return record

    def get_run(self, run_id: str) -> RunRecord | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT payload FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if not row:
            return None
        return RunRecord.model_validate_json(row[0])

    def list_agents(self) -> list[AgentInfo]:
        return [self._agent_info(agent) for agent in self._build_agents().values()]

    def _build_agents(self) -> dict[str, BaseAgent]:
        return {
            "ceo": CEOAgent("CEO Agent", "Planner and delegator", self.settings.ceo_model),
            "selector": ModelSelectorAgent(
                "Model Selector Agent", "Routes tasks to models", self.settings.model_selector_model
            ),
            "research": ResearchAgent(
                "Research Agent", "Search and market intelligence", self.settings.cheap_search_worker_model
            ),
            "coding": CodingAgent("Coding Agent", "Technical execution planning", self.settings.cheap_worker_model),
            "content": ContentAgent("Content Agent", "Content and narrative", self.settings.cheap_worker_model),
            "qa": QAAgent("QA Agent", "Review and quality control", self.settings.cheap_worker_model),
        }

    def _agent_info(self, agent: BaseAgent) -> AgentInfo:
        return AgentInfo(
            name=agent.name,
            role=agent.role,
            assigned_model=agent.assigned_model,
            status=agent.status,
            latest_action=agent.latest_action,
            completed_work=agent.completed_work,
        )

    def _build_metrics(self, events, started_at: datetime, completed_at: datetime, memory_count: int) -> RunMetrics:
        return RunMetrics(
            total_estimated_tokens=sum(event.estimated_input_tokens + event.estimated_output_tokens for event in events),
            total_estimated_cost_usd=round(sum(event.estimated_cost_usd for event in events), 6),
            agents_used=len({event.agent_name for event in events if event.agent_name != "TheHiveMind"}),
            tasks_completed=len(events),
            run_duration_seconds=round((completed_at - started_at).total_seconds(), 3),
            memory_chunks_retrieved=memory_count,
        )

    def _build_final_output(self, command: str) -> FinalOutput:
        return FinalOutput(
            summary=(
                f"TheHiveMind completed a mock multi-agent run for: {command}. "
                "The CEO planned the work, the selector routed models, workers produced specialized outputs, "
                "and QA assembled the final package."
            ),
            what_was_done=[
                "Converted the command into an execution plan.",
                "Retrieved relevant local memory snippets.",
                "Delegated research, technical, and content tasks.",
                "Estimated token usage and model cost per step.",
                "Reviewed outputs and assembled a final answer.",
            ],
            recommended_next_actions=[
                "Connect live provider adapters behind the existing provider interface.",
                "Replace lexical memory search with embeddings and pgvector or Chroma.",
                "Add streaming events so the timeline updates in real time.",
                "Persist project-specific artifacts and task approvals.",
            ],
            generated_artifacts=[
                "CEO execution plan",
                "Model routing map",
                "Research task brief",
                "Technical task list",
                "Content deliverable outline",
                "QA review summary",
            ],
        )

    def _ensure_database(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    command TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    def _save_run(self, record: RunRecord) -> None:
        payload = record.model_dump_json()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (run_id, command, status, created_at, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (record.run_id, record.command, record.status, record.started_at.isoformat(), payload),
            )

    def _log_usage_for_events(self, record: RunRecord) -> None:
        store = UsageStore(self.settings)
        for index, event in enumerate(record.events, start=1):
            metadata = get_model_metadata(event.model_used, self.settings.ceo_service_tier if event.model_used == self.settings.ceo_model else None)
            store.log_call(
                run_id=record.run_id,
                task_id=f"{record.run_id}:step-{index}",
                agent_name=event.agent_name,
                agent_role=event.agent_role,
                provider=metadata.provider,
                model=event.model_used,
                mode=record.mode,
                request_type=self._request_type_for_agent(event.agent_name),
                input_tokens=event.estimated_input_tokens,
                output_tokens=event.estimated_output_tokens,
                cached_tokens=0,
                reasoning_tokens=0,
                search_calls=0,
                search_cost_usd=0,
                estimated_cost_usd=event.estimated_cost_usd,
                latency_ms=max(1, int(record.metrics.run_duration_seconds * 1000 / max(1, len(record.events)))),
                success=event.status == "completed",
                created_at=event.timestamp,
                metadata={"usage_source": "orchestration_run"},
            )

    def _request_type_for_agent(self, agent_name: str) -> str:
        return {
            "CEO Agent": "planning",
            "Model Selector Agent": "model_routing",
            "Research Agent": "market_research",
            "Coding Agent": "code_generation",
            "Content Agent": "content_generation",
            "QA Agent": "validation",
            "TheHiveMind": "final_assembly",
        }.get(agent_name, "orchestration")
