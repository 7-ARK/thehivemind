import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.agent_registry.planner_service import AgentPlannerService
from app.agent_registry.schemas import AgentPlanRequest, AgentPlanResult
from app.agents.business_agent import BusinessAgent
from app.agents.ceo_agent import CEOAgent
from app.agents.file_builder_agent import FileBuilderAgent
from app.agents.llm_agent_runner import run_llm_agent
from app.agents.model_selector_agent import ModelSelectorAgent
from app.agents.operations_agent import OperationsAgent
from app.agents.qa_agent import QAAgent
from app.artifacts.artifact_store import ArtifactStore
from app.coding.coding_agent_runner import RealCodingAgentRunner
from app.coding.coding_policy import is_focused_website_update, prompt_file_scope
from app.coding.schemas import PatchValidationResult, RealCodingAgentResult
from app.core.config import Settings, get_settings
from app.core.cost_estimator import assert_run_budget, estimate_cost_usd, estimate_tokens
from app.core.model_registry import get_model_metadata
from app.core.models import AgentInfo, FinalOutput, RunEvent, RunMetrics, RunRecord
from app.memory.current_state import update_current_state
from app.memory.embedding_memory import EmbeddingMemory
from app.memory.context_packet import build_context_packet, format_context_packet
from app.memory.memory_ingestor import MemoryIngestor
from app.memory.retrieval import disabled_memory_summary, retrieve_memory
from app.memory.vector_memory import LocalVectorMemory
from app.orchestration.agent_context import AgentExecutionContext
from app.orchestration.task_packet import TaskPacket
from app.orchestration.task_graph import build_default_task_graph
from app.projects.project_state import update_project_state
from app.projects.project_workspace import ProjectWorkspaceManager
from app.projects.schemas import ProjectWorkspaceSummary
from app.providers.provider_router import generate_with_provider
from app.search_tools.exa_client import run_exa_search
from app.search_tools.schemas import SearchRequest, SearchResultPayload
from app.search_tools.search_store import SearchLogStore
from app.search_tools.source_formatter import mock_sources
from app.storage.usage_store import UsageStore
from app.workspace.command_runner import SafeCommandRunner
from app.workspace.file_writer import WorkspaceFileWriter
from app.workspace.schemas import CommandResult, WorkspaceSummary
from app.workspace.workspace_manager import WorkspaceManager


RunResult = RunRecord


def _selected_model_id(selected_models: dict[str, Any], agent_id: str, fallback: str) -> str:
    value = selected_models.get(agent_id)
    if isinstance(value, dict):
        model_id = value.get("selected_model_id")
        if isinstance(model_id, str) and model_id:
            return model_id
    return fallback


def _command_event_status(command_results: list[CommandResult]) -> str:
    if all(result.allowed and result.exit_code == 0 for result in command_results):
        return "completed"
    if any(result.allowed and result.exit_code != 0 for result in command_results):
        return "validation_failed"
    return "completed_with_warnings"


def _is_research_only_command(command: str) -> bool:
    lowered = command.lower()
    return "research only" in lowered or "only research" in lowered


def _agent_id_from_name(agent_name: str) -> str:
    return agent_name.lower().replace(" ", "_")


def _normalized_run_type(command: str, requested_run_type: str) -> str:
    if requested_run_type in {"prototype_build", "continuation", "business_launch_plan"} and is_focused_website_update(command):
        return "website_update"
    return requested_run_type


async def execute_run(
    command: str,
    mode: str = "mock",
    project_id: str | None = None,
    run_type: str = "business_launch_plan",
    allow_ceo_live: bool = False,
    allow_file_writes: bool = False,
    allow_safe_commands: bool = False,
    allow_web_search: bool = False,
    use_memory: bool = True,
    use_real_coding_agent: bool = True,
    allow_live_coding_model_call: bool = False,
    real_coding_dry_run: bool = False,
    real_coding_model: str | None = None,
    real_coding_max_files: int | None = None,
    real_coding_max_repair_attempts: int = 0,
    max_cost_usd: float | None = None,
) -> RunResult:
    return await ExecutionEngine().execute_run(
        command=command,
        mode=mode,
        project_id=project_id,
        run_type=run_type,
        allow_ceo_live=allow_ceo_live,
        allow_file_writes=allow_file_writes,
        allow_safe_commands=allow_safe_commands,
        allow_web_search=allow_web_search,
        use_memory=use_memory,
        use_real_coding_agent=use_real_coding_agent,
        allow_live_coding_model_call=allow_live_coding_model_call,
        real_coding_dry_run=real_coding_dry_run,
        real_coding_model=real_coding_model,
        real_coding_max_files=real_coding_max_files,
        real_coding_max_repair_attempts=real_coding_max_repair_attempts,
        max_cost_usd=max_cost_usd,
    )


class ExecutionEngine:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.db_path = self.settings.sqlite_path
        self.artifacts = ArtifactStore(self.settings)
        self.usage = UsageStore(self.settings)
        self._ensure_database()

    def _plan_run(
        self,
        *,
        command: str,
        run_type: str,
        project_id: str | None,
        mode: str,
        allow_file_writes: bool,
        allow_safe_commands: bool,
        allow_web_search: bool,
        max_cost: float,
    ) -> AgentPlanResult:
        return AgentPlannerService(self.settings).plan(
            AgentPlanRequest(
                command=command,
                run_type=run_type,
                project_id=project_id,
                mode=mode,
                allow_file_writes=allow_file_writes,
                allow_safe_commands=allow_safe_commands,
                allow_search=allow_web_search,
                max_cost_usd=max_cost,
            )
        )

    def _selection_by_agent(self, plan: AgentPlanResult) -> dict[str, Any]:
        return {
            item.agent_id: item.selected_model
            for item in plan.selected_agents
            if item.selected_model
        }

    async def execute_run(
        self,
        *,
        command: str,
        mode: str = "mock",
        project_id: str | None = None,
        run_type: str = "business_launch_plan",
        allow_ceo_live: bool = False,
        allow_file_writes: bool = False,
        allow_safe_commands: bool = False,
        allow_web_search: bool = False,
        use_memory: bool = True,
        use_real_coding_agent: bool = True,
        allow_live_coding_model_call: bool = False,
        real_coding_dry_run: bool = False,
        real_coding_model: str | None = None,
        real_coding_max_files: int | None = None,
        real_coding_max_repair_attempts: int = 0,
        max_cost_usd: float | None = None,
    ) -> RunRecord:
        self._use_memory_for_current_run = use_memory
        run_type = _normalized_run_type(command, run_type)
        if mode not in {"mock", "live"}:
            raise HTTPException(status_code=400, detail="mode must be 'mock' or 'live'.")
        if mode == "live":
            self.settings.require_live_allowed()
        else:
            mode = "mock"

        run_id = str(uuid.uuid4())
        started_at = datetime.now(UTC)
        max_cost = min(max_cost_usd or self.settings.max_cost_per_run_usd, self.settings.max_cost_per_run_usd)
        memory = retrieve_memory(command, project_id=project_id, run_type=run_type) if use_memory else disabled_memory_summary()
        if run_type == "provider_test":
            return await self._execute_provider_test(
                command=command,
                mode=mode,
                project_id=project_id,
                max_cost=max_cost,
                run_id=run_id,
                started_at=started_at,
                memory=memory,
            )
        if run_type in {"research", "research_only"} or _is_research_only_command(command):
            return await self._execute_research_only(
                command=command,
                mode=mode,
                project_id=project_id,
                allow_web_search=allow_web_search,
                max_cost=max_cost,
                run_id=run_id,
                started_at=started_at,
                memory=memory,
            )
        if run_type == "website_update":
            return await self._execute_website_update(
                command=command,
                mode=mode,
                project_id=project_id,
                allow_file_writes=allow_file_writes,
                allow_safe_commands=allow_safe_commands,
                allow_web_search=allow_web_search,
                max_cost=max_cost,
                run_id=run_id,
                started_at=started_at,
                memory=memory,
                use_real_coding_agent=use_real_coding_agent,
                allow_live_coding_model_call=allow_live_coding_model_call,
                real_coding_dry_run=real_coding_dry_run,
                real_coding_model=real_coding_model,
                real_coding_max_files=real_coding_max_files,
                real_coding_max_repair_attempts=real_coding_max_repair_attempts,
            )
        if run_type in {"prototype_build", "continuation"}:
            return await self._execute_prototype_build(
                command=command,
                mode=mode,
                project_id=project_id,
                run_type=run_type,
                allow_ceo_live=allow_ceo_live,
                allow_file_writes=allow_file_writes,
                allow_safe_commands=allow_safe_commands,
                allow_web_search=allow_web_search,
                max_cost=max_cost,
                run_id=run_id,
                started_at=started_at,
                memory=memory,
            )
        agents = self._build_agents(allow_ceo_live=allow_ceo_live, mode=mode)
        events: list[RunEvent] = []
        artifact_records = []

        ceo_output = await self._run_step(
            run_id=run_id,
            command=command,
            mode=mode,
            agent_name="CEO Agent",
            agent_role=agents["ceo"].role,
            model=agents["ceo"].assigned_model,
            request_type="planning",
            prompt=self._ceo_prompt(command, memory.current_state),
            mock_output=self._ceo_plan(command),
        )
        ceo_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="ceo_plan.md",
            artifact_type="markdown",
            content=ceo_output["text"],
            agent_name="CEO Agent",
            summary="CEO plan with scope, success criteria, risks, and agent assignments.",
        )
        artifact_records.append(ceo_artifact)
        events.append(self._event_from_step(ceo_output, "Created CEO plan", command, ceo_artifact.id))

        model_selection = self._model_selection(agents, mode, allow_ceo_live)
        selector_output = await self._run_step(
            run_id=run_id,
            command=command,
            mode=mode,
            agent_name="Model Selector Agent",
            agent_role=agents["selector"].role,
            model=agents["selector"].assigned_model,
            request_type="model_routing",
            prompt=f"Select safe models for this plan:\n{ceo_output['text']}",
            mock_output=json.dumps(model_selection, indent=2),
        )
        selector_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="model_selection.json",
            artifact_type="json",
            content=selector_output["text"],
            agent_name="Model Selector Agent",
            summary="Model choices, reasons, mode, and safe execution notes.",
        )
        artifact_records.append(selector_artifact)
        events.append(self._event_from_step(selector_output, "Selected models for each agent", ceo_output["text"], selector_artifact.id))

        research_output = await self._run_step(
            run_id=run_id,
            command=command,
            mode=mode,
            agent_name="Research Agent",
            agent_role=agents["research"].role,
            model=agents["research"].assigned_model,
            request_type="market_research",
            prompt=f"Create a conservative research brief. Do not use web search.\nCommand: {command}",
            mock_output=agents["research"].create_research_brief(command),
        )
        research_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="research_brief.md",
            artifact_type="markdown",
            content=research_output["text"],
            agent_name="Research Agent",
            summary="Market assumptions, customer segments, placeholders, and verification questions.",
        )
        artifact_records.append(research_artifact)
        events.append(self._event_from_step(research_output, "Produced research brief", command, research_artifact.id))

        content_output = await self._run_step(
            run_id=run_id,
            command=command,
            mode=mode,
            agent_name="Content Agent",
            agent_role=agents["content"].role,
            model=agents["content"].assigned_model,
            request_type="content_generation",
            prompt=f"Create launch content from this research:\n{research_output['text']}",
            mock_output=agents["content"].create_content_calendar(command),
        )
        content_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="content_calendar.md",
            artifact_type="markdown",
            content=content_output["text"],
            agent_name="Content Agent",
            summary="Brand positioning, social launch ideas, captions, and 14-day calendar.",
        )
        artifact_records.append(content_artifact)
        events.append(self._event_from_step(content_output, "Created launch content calendar", research_output["text"], content_artifact.id))

        operations_output = await self._run_step(
            run_id=run_id,
            command=command,
            mode=mode,
            agent_name="Operations Agent",
            agent_role=agents["operations"].role,
            model=agents["operations"].assigned_model,
            request_type="operations_planning",
            prompt=f"Create an operations checklist from this plan and content:\n{ceo_output['text']}\n{content_output['text']}",
            mock_output=agents["operations"].create_operations_checklist(command),
        )
        operations_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="operations_checklist.md",
            artifact_type="markdown",
            content=operations_output["text"],
            agent_name="Operations Agent",
            summary="Order flow, WhatsApp handling, backend features, journey, and manual approvals.",
        )
        artifact_records.append(operations_artifact)
        events.append(self._event_from_step(operations_output, "Created operations checklist", content_output["text"], operations_artifact.id))

        qa_text = self._qa_review(command, [ceo_output["text"], research_output["text"], content_output["text"], operations_output["text"]])
        qa_output = await self._run_step(
            run_id=run_id,
            command=command,
            mode=mode,
            agent_name="QA Agent",
            agent_role=agents["qa"].role,
            model=agents["qa"].assigned_model,
            request_type="validation",
            prompt=f"Review these artifacts for hallucinations, assumptions, and practicality:\n{qa_text}",
            mock_output=qa_text,
        )
        qa_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="qa_review.md",
            artifact_type="markdown",
            content=qa_output["text"],
            agent_name="QA Agent",
            summary="Quality review, assumptions, human approvals, and approval status.",
        )
        artifact_records.append(qa_artifact)
        events.append(self._event_from_step(qa_output, "Reviewed run package", operations_output["text"], qa_artifact.id))

        final_report = self._final_report(command, project_id, artifact_records, [ceo_output, selector_output, research_output, content_output, operations_output, qa_output])
        final_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="final_report.md",
            artifact_type="markdown",
            content=final_report,
            agent_name="TheHiveMind",
            summary="Final controlled run report and next actions.",
        )
        artifact_records.append(final_artifact)
        final_event = self._manual_step(
            run_id=run_id,
            mode=mode,
            agent_name="TheHiveMind",
            agent_role="Final assembly",
            model=self._safe_ceo_model(mode, allow_ceo_live),
            request_type="final_assembly",
            input_text=qa_output["text"],
            output_text=final_report,
            action_summary="Assembled final report and artifact manifest",
            artifact_id=final_artifact.id,
        )
        events.append(final_event)

        summary_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="run_summary.json",
            artifact_type="json",
            content=json.dumps(
                {
                    "run_id": run_id,
                    "project_id": project_id,
                    "run_type": run_type,
                    "mode": mode,
                    "model_choices": model_selection,
                    "artifact_ids": [artifact.id for artifact in artifact_records],
                    "estimated_cost_usd": round(sum(event.estimated_cost_usd for event in events), 6),
                    "estimated_tokens": sum((event.estimated_tokens or 0) for event in events),
                },
                indent=2,
            ),
            agent_name="TheHiveMind",
            summary="Machine-readable run summary, model choices, artifact IDs, and cost summary.",
        )
        artifact_records.append(summary_artifact)

        completed_at = datetime.now(UTC)
        metrics = RunMetrics(
            total_estimated_tokens=sum(event.estimated_tokens or event.estimated_input_tokens + event.estimated_output_tokens for event in events),
            total_estimated_cost_usd=round(sum(event.estimated_cost_usd for event in events), 6),
            agents_used=len({event.agent_name for event in events if event.agent_name != "TheHiveMind"}),
            tasks_completed=len(events),
            run_duration_seconds=round((completed_at - started_at).total_seconds(), 3),
            memory_chunks_retrieved=len(memory.retrieved_snippets),
        )
        assert_run_budget(metrics.total_estimated_cost_usd)
        if metrics.total_estimated_cost_usd > max_cost:
            raise HTTPException(status_code=400, detail=f"Estimated run cost ${metrics.total_estimated_cost_usd:.6f} exceeds request max_cost_usd=${max_cost:.2f}.")

        final_output = FinalOutput(
            summary=f"Run Engine v1 completed a controlled {run_type} workflow for: {command}",
            what_was_done=[
                "Created CEO plan and scope.",
                "Selected safe models for each agent.",
                "Produced research, content, operations, QA, and final report artifacts.",
                "Updated memory with artifact summaries and model choices.",
                "Logged usage by provider, model, agent, task type, tokens, and estimated cost.",
            ],
            recommended_next_actions=[
                "Review artifacts and approve assumptions before public use.",
                "Verify market, legal, nutrition, and delivery claims manually.",
                "Keep live mode disabled until a small provider test is approved.",
            ],
            generated_artifacts=[artifact.name for artifact in artifact_records],
        )

        record = RunRecord(
            run_id=run_id,
            command=command,
            mode=mode,
            project_id=project_id,
            run_type=run_type,
            status="completed",
            started_at=started_at,
            completed_at=completed_at,
            events=events,
            agents=[self._agent_info(agent) for agent in agents.values()],
            task_graph=build_default_task_graph(),
            metrics=metrics,
            memory=memory,
            final_output=final_output,
            artifacts=artifact_records,
        )
        self._update_memory(record, model_selection)
        return self._finalize_run(record)

    async def _execute_research_only(
        self,
        *,
        command: str,
        mode: str,
        project_id: str | None,
        allow_web_search: bool,
        max_cost: float,
        run_id: str,
        started_at: datetime,
        memory,
    ) -> RunRecord:
        active_project_id = project_id or "unassigned"
        agent_plan = self._plan_run(
            command=command,
            run_type="research_only",
            project_id=project_id,
            mode=mode,
            allow_file_writes=False,
            allow_safe_commands=False,
            allow_web_search=allow_web_search,
            max_cost=max_cost,
        )
        selected_models = self._selection_by_agent(agent_plan)
        research_model = _selected_model_id(selected_models, "research_agent", self.settings.cheap_search_worker_model)
        qa_model = _selected_model_id(selected_models, "qa_agent", self.settings.cheap_worker_model)
        provider_id = (agent_plan.selected_search_provider or {}).get("id") if isinstance(agent_plan.selected_search_provider, dict) else None
        memory_packet = self._memory_packet_for_agent(
            agent_id="research_agent",
            project_id=active_project_id,
            run_id=run_id,
            run_type="research_only",
            task=command,
            current_command=command,
            mode=mode,
        )
        search_result = await self._run_research_search(
            command=command,
            mode=mode,
            allow_web_search=allow_web_search,
            provider_id=provider_id,
            run_id=run_id,
            project_id=project_id,
        )
        sources = search_result.sources
        research_text = self._research_only_report(command, agent_plan.model_dump(), [source.model_dump() for source in sources], search_result.brief, memory_packet=memory_packet, search_result=search_result)
        artifacts = []
        agent_plan_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="agent_plan.json",
            artifact_type="json",
            content=agent_plan.model_dump_json(indent=2),
            agent_name="Model Selector Agent",
            summary="Research-only plan with search selection status.",
        )
        model_selection_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="model_selection.json",
            artifact_type="json",
            content=json.dumps(selected_models, indent=2),
            agent_name="Model Selector Agent",
            summary="Per-agent model choices for research-only run.",
        )
        research_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="research_brief.md",
            artifact_type="markdown",
            content=research_text,
            agent_name="Research Agent",
            summary="Research-only brief and source limitations.",
        )
        sources_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="research_sources.json",
            artifact_type="json",
            content=json.dumps(self._research_sources_payload(agent_plan.model_dump(), search_result), indent=2),
            agent_name="Research Agent",
            summary="Search sources used, or empty when search was unavailable/disabled.",
        )
        artifacts.extend([agent_plan_artifact, model_selection_artifact, research_artifact, sources_artifact])
        events = [
            self._manual_step(
                run_id=run_id,
                mode=mode,
                agent_name="Research Agent",
                agent_role="Research and source collection",
                model=research_model,
                request_type="research_only",
                input_text=command,
                output_text=research_text,
                action_summary="Produced research-only brief",
                artifact_id=research_artifact.id,
            )
        ]
        qa_text = self._prototype_qa_review(command, research_text, [], file_changes_count=0, search_result=search_result, memory_packet=memory_packet, workflow="research_only")
        qa_output = await self._run_step(
            run_id=run_id,
            command=command,
            mode=mode,
            agent_name="QA Agent",
            agent_role="Review and quality control",
            model=qa_model,
            request_type="validation",
            prompt=qa_text,
            mock_output=qa_text,
        )
        qa_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="qa_review.md",
            artifact_type="markdown",
            content=qa_output["text"],
            agent_name="QA Agent",
            summary="QA review for research-only run.",
        )
        artifacts.append(qa_artifact)
        events.append(self._event_from_step(qa_output, "Reviewed research-only output", research_text, qa_artifact.id))
        completed_at = datetime.now(UTC)
        metrics = RunMetrics(
            total_estimated_tokens=sum(event.estimated_tokens or event.estimated_input_tokens + event.estimated_output_tokens for event in events),
            total_estimated_cost_usd=round(sum(event.estimated_cost_usd for event in events), 6),
            agents_used=len({event.agent_name for event in events if event.agent_name != "TheHiveMind"}),
            tasks_completed=len(events),
            run_duration_seconds=round((completed_at - started_at).total_seconds(), 3),
            memory_chunks_retrieved=len(memory.retrieved_snippets),
        )
        if metrics.total_estimated_cost_usd > max_cost:
            raise HTTPException(status_code=400, detail=f"Estimated run cost ${metrics.total_estimated_cost_usd:.6f} exceeds request max_cost_usd=${max_cost:.2f}.")
        record = RunRecord(
            run_id=run_id,
            command=command,
            mode=mode,
            project_id=project_id,
            run_type="research_only",
            status="completed",
            started_at=started_at,
            completed_at=completed_at,
            events=events,
            agents=[
                AgentInfo(name="Research Agent", role="Research and source collection", assigned_model=research_model, status="completed", latest_action="Produced research-only brief", completed_work=["Created research_brief.md", "Created research_sources.json"]),
                AgentInfo(name="QA Agent", role="Review and quality control", assigned_model=qa_model, status="completed", latest_action="Reviewed research-only output", completed_work=["Reviewed research brief."]),
            ],
            task_graph=build_default_task_graph(),
            metrics=metrics,
            memory=memory,
            final_output=FinalOutput(
                summary="Research-only workflow completed without Website Agent or file writes.",
                what_was_done=["Selected research-only workflow.", "Produced a research brief.", "Stored source metadata or limitations.", "Skipped Website Agent and file writes."],
                recommended_next_actions=[self._search_next_action(search_result), "Review sources and limitations before using claims."],
                generated_artifacts=[artifact.name for artifact in artifacts],
            ),
            artifacts=artifacts,
            models_used=sorted({event.model_used for event in events}),
            usage_summary={
                "estimated_cost_usd": metrics.total_estimated_cost_usd,
                "estimated_tokens": metrics.total_estimated_tokens,
                "agents_used": metrics.agents_used,
                "models_used": sorted({event.model_used for event in events}),
                "selected_workflow": agent_plan.selected_workflow,
                "search_provider_id": provider_id,
                "search_needed": agent_plan.search_needed,
                "search_unavailable": agent_plan.search_unavailable,
            },
            agent_plan=agent_plan.model_dump(),
            model_selection=selected_models,
        )
        return self._finalize_run(record)

    async def _execute_provider_test(
        self,
        *,
        command: str,
        mode: str,
        project_id: str | None,
        max_cost: float,
        run_id: str,
        started_at: datetime,
        memory,
    ) -> RunRecord:
        if mode != "live":
            raise HTTPException(status_code=400, detail="provider_test requires mode=live.")
        model = self.settings.cheap_search_worker_model
        metadata = get_model_metadata(model)
        messages = [
            {"role": "system", "content": "You are a tiny provider connectivity test. Reply with exactly: live test ok"},
            {"role": "user", "content": command},
        ]
        response, _usage_log_id = await generate_with_provider(
            provider=metadata.provider,
            model=model,
            mode="live",
            messages=messages,
            max_output_tokens=min(20, self.settings.max_output_tokens_per_call),
            temperature=0,
            run_id=run_id,
            task_id=f"{run_id}:provider_test",
            agent_name="Provider Test Agent",
            agent_role="Connectivity and usage validation",
            project_id=project_id,
            request_type="provider_test",
            settings=self.settings,
            usage_store=self.usage,
        )
        cost = response.estimated_cost_usd
        if cost > max_cost:
            raise HTTPException(status_code=400, detail=f"Provider test cost ${cost:.6f} exceeds request max_cost_usd=${max_cost:.2f}.")
        completed_at = datetime.now(UTC)
        event = RunEvent(
            timestamp=completed_at,
            run_id=run_id,
            agent_name="Provider Test Agent",
            agent_role="Connectivity and usage validation",
            status="completed",
            action_summary="Ran one tiny live provider test",
            input_summary="Tiny live provider test with no files or commands.",
            output_summary=response.text[:500],
            model_used=response.model,
            provider=response.provider,
            estimated_input_tokens=response.input_tokens,
            estimated_output_tokens=response.output_tokens,
            estimated_tokens=response.input_tokens + response.output_tokens,
            estimated_cost_usd=cost,
            estimated_cost=cost,
        )
        record = RunRecord(
            run_id=run_id,
            command=command,
            mode=mode,
            project_id=project_id,
            run_type="provider_test",
            status="completed",
            started_at=started_at,
            completed_at=completed_at,
            events=[event],
            agents=[
                AgentInfo(
                    name="Provider Test Agent",
                    role="Connectivity and usage validation",
                    assigned_model=response.model,
                    status="completed",
                    latest_action="Ran one tiny live provider test",
                    completed_work=["Captured provider response usage when returned by provider."],
                )
            ],
            task_graph=build_default_task_graph(),
            metrics=RunMetrics(
                total_estimated_tokens=response.input_tokens + response.output_tokens,
                total_estimated_cost_usd=cost,
                agents_used=1,
                tasks_completed=1,
                run_duration_seconds=round((completed_at - started_at).total_seconds(), 3),
                memory_chunks_retrieved=len(memory.retrieved_snippets),
            ),
            memory=memory,
            final_output=FinalOutput(
                summary="Provider test completed without file writes or command execution.",
                what_was_done=["Ran one tiny live provider call.", "Captured provider response usage if available."],
                recommended_next_actions=["Review Usage & Costs for provider-response usage and official sync status."],
                generated_artifacts=[],
            ),
            artifacts=[],
            project_files_created=[],
            project_files_updated=[],
            commands_run=[],
            usage_summary={
                "provider_response_cost_usd": response.raw_metadata.get("provider_reported_cost_usd"),
                "provider_response_tokens": response.input_tokens + response.output_tokens,
                "official_usage_sync": "scheduled_after_live_run",
            },
        )
        return self._finalize_run(record)

    async def _execute_website_update(
        self,
        *,
        command: str,
        mode: str,
        project_id: str | None,
        allow_file_writes: bool,
        allow_safe_commands: bool,
        allow_web_search: bool,
        max_cost: float,
        run_id: str,
        started_at: datetime,
        memory,
        use_real_coding_agent: bool = True,
        allow_live_coding_model_call: bool = False,
        real_coding_dry_run: bool = False,
        real_coding_model: str | None = None,
        real_coding_max_files: int | None = None,
        real_coding_max_repair_attempts: int = 0,
    ) -> RunRecord:
        if not allow_file_writes:
            raise HTTPException(status_code=403, detail="website_update requires allow_file_writes=true unless the prompt restricted file writes.")

        active_project_id = project_id or "default-project"
        project_manager = ProjectWorkspaceManager(self.settings)
        project_workspace = project_manager.ensure_project_workspace(active_project_id)
        project_root = project_manager.get_project_root(active_project_id)
        project_manager.create_run_log_folder(run_id)
        command_runner = SafeCommandRunner(self.settings)
        agent_plan = self._plan_run(
            command=command,
            run_type="website_update",
            project_id=active_project_id,
            mode=mode,
            allow_file_writes=allow_file_writes,
            allow_safe_commands=allow_safe_commands,
            allow_web_search=allow_web_search,
            max_cost=max_cost,
        )
        selected_models = self._selection_by_agent(agent_plan)
        research_model = _selected_model_id(selected_models, "research_agent", self.settings.cheap_search_worker_model)
        website_model = _selected_model_id(selected_models, "website_agent", self.settings.cheap_worker_model)
        qa_model = _selected_model_id(selected_models, "qa_agent", self.settings.cheap_worker_model)

        artifact_records = []
        events: list[RunEvent] = []
        agent_plan_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="agent_plan.json",
            artifact_type="json",
            content=agent_plan.model_dump_json(indent=2),
            agent_name="Model Selector Agent",
            summary="Selected website_update workflow, selected/skipped agents, and applied constraints.",
        )
        model_selection_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="model_selection.json",
            artifact_type="json",
            content=json.dumps(selected_models, indent=2),
            agent_name="Model Selector Agent",
            summary="Per-agent model choices with reasons and fallbacks.",
        )
        artifact_records.extend([agent_plan_artifact, model_selection_artifact])

        research_context = ""
        search_result: SearchResultPayload | None = None
        memory_packet = self._memory_packet_for_agent(
            agent_id="website_agent",
            project_id=active_project_id,
            run_id=run_id,
            run_type="website_update",
            task=command,
            current_command=command,
            mode=mode,
        )
        if any(agent.agent_id == "research_agent" for agent in agent_plan.selected_agents):
            provider_id = (agent_plan.selected_search_provider or {}).get("id") if isinstance(agent_plan.selected_search_provider, dict) else None
            search_result = await self._run_research_search(
                command=command,
                mode=mode,
                allow_web_search=allow_web_search,
                provider_id=provider_id,
                run_id=run_id,
                project_id=active_project_id,
            )
            sources = search_result.sources
            research_context = self._research_only_report(command, agent_plan.model_dump(), [source.model_dump() for source in sources], search_result.brief, memory_packet=memory_packet, search_result=search_result)
            research_artifact = self.artifacts.save_text(
                run_id=run_id,
                name="research_brief.md",
                artifact_type="markdown",
                content=research_context,
                agent_name="Research Agent",
                summary="Research context for website update.",
            )
            sources_artifact = self.artifacts.save_text(
                run_id=run_id,
                name="research_sources.json",
                artifact_type="json",
                content=json.dumps(self._research_sources_payload(agent_plan.model_dump(), search_result), indent=2),
                agent_name="Research Agent",
                summary="Search sources used, or empty when search was unavailable/disabled.",
            )
            artifact_records.extend([research_artifact, sources_artifact])
            events.append(
                self._manual_step(
                    run_id=run_id,
                    mode=mode,
                    agent_name="Research Agent",
                    agent_role="Research and source collection",
                    model=research_model,
                    request_type="website_research",
                    input_text=command,
                    output_text=research_context,
                    action_summary="Prepared research context for website update",
                    artifact_id=research_artifact.id,
                )
            )

        homepage_copy_task = self._is_homepage_copy_task(command)
        real_coding_result = None
        command_results: list[CommandResult] = []
        if use_real_coding_agent and self.settings.enable_real_coding_agent:
            coding_model = real_coding_model or _selected_model_id(selected_models, "website_agent", self.settings.real_coding_agent_model)
            selected_models["real_coding_agent"] = {
                "selected_model_id": coding_model,
                "provider": "openrouter" if mode == "live" else "mock",
                "fallback_model_id": self.settings.real_coding_agent_fallback_model,
                "reason": "Real Coding Agent uses the configured OpenRouter coding worker. GPT-5.5 remains CEO-gated and is not used for coding worker tasks.",
                "live_call_made": mode == "live" and allow_live_coding_model_call,
                "mock_simulated": mode == "mock",
            }
            real_coding_result, file_entries, command_results, coding_event = await RealCodingAgentRunner(self.settings).run(
                project_id=active_project_id,
                run_id=run_id,
                command=command,
                mode=mode,
                allow_safe_commands=allow_safe_commands,
                memory_packet=memory_packet,
                model_id=coding_model,
                fallback_model_id=self.settings.real_coding_agent_fallback_model,
                allow_live_coding_model_call=allow_live_coding_model_call,
                dry_run=real_coding_dry_run,
                max_files=real_coding_max_files,
                max_repair_attempts=real_coding_max_repair_attempts,
                max_cost_usd=max_cost,
            )
            artifact_records.extend(self._save_real_coding_artifacts(run_id, real_coding_result))
            events.append(coding_event)
        else:
            website_agent = FileBuilderAgent("Website Agent", "Updates website project files", website_model)
            if homepage_copy_task:
                file_entries = website_agent.build_project_greek_yogurt_homepage_copy_update(
                    active_project_id,
                    run_id,
                    command,
                    memory_themes=self._memory_theme_lines(memory_packet),
                )
            else:
                file_entries = website_agent.build_project_greek_yogurt_site(active_project_id, run_id, command)
            real_coding_result = self._template_fallback_result(command, website_model, [entry.path for entry in file_entries], homepage_copy_task)
            artifact_records.extend(self._save_real_coding_artifacts(run_id, real_coding_result))

        scope_plan_text = self._website_scope_plan(
            command,
            homepage_copy_task,
            changed_files=[entry.path for entry in file_entries],
            system_metadata_files=["project_state.md", "manifest.json"],
        )
        scope_plan_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="website_scope_plan.md",
            artifact_type="markdown",
            content=scope_plan_text,
            agent_name="Real Coding Agent" if real_coding_result and real_coding_result.used and not real_coding_result.hardcoded_fallback_used else "Website Agent",
            summary="Website file-scope plan for the requested update.",
        )
        artifact_records.append(scope_plan_artifact)
        workspace_artifacts = []
        for entry in file_entries:
            artifact = self.artifacts.register_file(
                run_id=run_id,
                name=entry.path,
                artifact_type="project_file",
                path=str(project_root / entry.path),
                agent_name="Real Coding Agent" if real_coding_result and real_coding_result.used and not real_coding_result.hardcoded_fallback_used else "Website Agent",
                summary=entry.after_summary,
            )
            workspace_artifacts.append(artifact)
            artifact_records.append(artifact)
        memory_usage_text = self._website_memory_used_text(memory_packet, search_result)
        website_text = "\n".join(f"- {entry.operation}: {entry.path} ({entry.size_bytes} bytes)" for entry in file_entries)
        website_text = f"{memory_usage_text}\n\n## File Updates\n{website_text}"
        if not (real_coding_result and real_coding_result.used and not real_coding_result.hardcoded_fallback_used):
            events.append(
                self._manual_step(
                    run_id=run_id,
                    mode=mode,
                    agent_name="Website Agent",
                    agent_role="Template fallback for website project files",
                    model=website_model,
                    request_type="website_update_template_fallback",
                    input_text=command,
                    output_text=f"Template fallback used. No real coding model call was made.\n\n{website_text}",
                    action_summary="Updated website project files with deterministic template fallback",
                    artifact_id=workspace_artifacts[0].id if workspace_artifacts else model_selection_artifact.id,
                )
            )

        if not command_results and allow_safe_commands and file_entries:
            command_results.append(command_runner.run_project_command(active_project_id, run_id, ["python", "-m", "py_compile", "website/app.py"]))
        elif not command_results and not allow_safe_commands:
            command_results.append(
                CommandResult(
                    command=["python", "-m", "py_compile", "website/app.py"],
                    cwd=".",
                    exit_code=-1,
                    stdout="",
                    stderr="",
                    duration_ms=0,
                    allowed=False,
                    blocked_reason="Blocked by safety policy: safe commands disabled for this run.",
                    executable_command=["python", "-m", "py_compile", "website/app.py"],
                    resolved_cwd=str(project_root),
                )
            )
        command_text = "\n".join(
            f"- {'allowed' if result.allowed else 'blocked'} {result.command}: exit={result.exit_code} cwd={result.cwd} stderr={result.stderr[:300]} reason={result.blocked_reason or result.error_message or 'n/a'}"
            for result in command_results
        ) or "Safe Command Runner completed; no validation command was required or executed."
        if allow_safe_commands:
            safe_command_action = (
                "Ran project sanity validation with safe command runner"
                if command_results
                else "Safe Command Runner completed; no validation command was required or executed."
            )
            safe_command_input = (
                "Run project sanity validation after the website update. This is a general syntax check, not direct validation of unchanged HTML/JSON copy."
                if command_results
                else "Check whether any approved safe validation command is required after the website update."
            )
            command_event = self._manual_step(
                    run_id=run_id,
                    mode=mode,
                    agent_name="Safe Command Runner",
                    agent_role="Validation sandbox",
                    model=self.settings.cheap_worker_model,
                    request_type="command_validation",
                    input_text=safe_command_input,
                    output_text=command_text,
                    action_summary=safe_command_action,
                    artifact_id=workspace_artifacts[0].id if workspace_artifacts else model_selection_artifact.id,
                )
            command_event.status = _command_event_status(command_results)  # type: ignore[assignment]
            if real_coding_result and real_coding_result.repair_loop.final_result == "repaired_successfully":
                command_event.status = "completed"  # type: ignore[assignment]
                command_event.action_summary = "Safe command validation passed after one repair attempt"
            command_event.action_summary = "Safe command validation failed" if command_event.status == "validation_failed" else command_event.action_summary
            events.append(command_event)

        qa_input = f"Agent plan:\n{agent_plan.model_dump_json(indent=2)}\n\nResearch:\n{research_context}\n\nMemory:\n{memory_usage_text}\n\nScope plan:\n{scope_plan_text}\n\nFiles:\n{website_text}\n\nCommands:\n{command_text}"
        qa_output = await self._run_step(
            run_id=run_id,
            command=command,
            mode=mode,
            agent_name="QA Agent",
            agent_role="Review and quality control",
            model=qa_model,
            request_type="validation",
            prompt=qa_input,
            mock_output=self._prototype_qa_review(
                command,
                qa_input,
                command_results,
                file_changes_count=len(file_entries),
                search_result=search_result,
                memory_packet=memory_packet,
                changed_paths=[entry.path for entry in file_entries],
                system_metadata_paths=["project_state.md", "manifest.json"],
                homepage_copy_scope=homepage_copy_task,
                allowed_user_file_scope=real_coding_result.allowed_user_file_scope.model_dump() if real_coding_result else None,
                workflow="website_update",
                real_coding_result=real_coding_result,
            ),
        )
        qa_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="qa_review.md",
            artifact_type="markdown",
            content=qa_output["text"],
            agent_name="QA Agent",
            summary="QA review of website-only update and constraints.",
        )
        artifact_records.append(qa_artifact)
        events.append(self._event_from_step(qa_output, "Reviewed website update", "Review website update outputs and constraints.", qa_artifact.id))

        completed_at = datetime.now(UTC)
        metrics = RunMetrics(
            total_estimated_tokens=sum(event.estimated_tokens or event.estimated_input_tokens + event.estimated_output_tokens for event in events),
            total_estimated_cost_usd=round(sum(event.estimated_cost_usd for event in events), 6),
            agents_used=len({event.agent_name for event in events if event.agent_name != "TheHiveMind"}),
            tasks_completed=len(events),
            run_duration_seconds=round((completed_at - started_at).total_seconds(), 3),
            memory_chunks_retrieved=len(memory.retrieved_snippets),
        )
        assert_run_budget(metrics.total_estimated_cost_usd)
        if metrics.total_estimated_cost_usd > max_cost:
            raise HTTPException(status_code=400, detail=f"Estimated run cost ${metrics.total_estimated_cost_usd:.6f} exceeds request max_cost_usd=${max_cost:.2f}.")

        run_status = (
            "failed"
            if real_coding_result
            and (
                (real_coding_result.live_call_made and not real_coding_result.validation.accepted)
                or real_coding_result.repair_loop.rollback_attempted
                or real_coding_result.repair_loop.final_result == "failed_rollback_error"
            )
            else "completed"
        )
        created_files = [entry.path for entry in file_entries if entry.operation == "created"]
        edited_files = [entry.path for entry in file_entries if entry.operation == "updated"]
        command_success = (
            True
            if real_coding_result and real_coding_result.repair_loop.final_result == "repaired_successfully"
            else all(result.allowed and result.exit_code == 0 for result in command_results)
        )
        project_state_content = update_project_state(
            project_root / "project_state.md",
            project_id=active_project_id,
            run_id=run_id,
            command=command,
            files_created=created_files,
            files_edited=edited_files,
            command_success=command_success,
            next_steps=["Review website changes locally.", "Keep deploys, installs, external actions, and public claims behind approval."],
        )
        state_entry = project_manager.write_project_file(active_project_id, "project_state.md", project_state_content, "Project Workspace Manager", run_id, "Latest project state after website_update.")
        project_manifest = project_manager.append_project_run(active_project_id, run_id, f"Website update completed for: {command}")
        manifest_artifact = self.artifacts.register_file(
            run_id=run_id,
            name="project_manifest.json",
            artifact_type="project_manifest",
            path=str(project_root / "manifest.json"),
            agent_name="Project Workspace Manager",
            summary="Persistent project manifest with website_update files.",
        )
        state_artifact = self.artifacts.register_file(
            run_id=run_id,
            name="project_state.md",
            artifact_type="project_state",
            path=str(project_root / "project_state.md"),
            agent_name="Project Workspace Manager",
            summary="Updated project state.",
        )
        artifact_records.extend([manifest_artifact, state_artifact])
        project_manager.write_run_logs(
            run_id=run_id,
            run_summary={
                "run_id": run_id,
                "project_id": active_project_id,
                "run_type": "website_update",
                "status": run_status,
                "selected_workflow": agent_plan.selected_workflow,
                "agent_plan": agent_plan.model_dump(),
                "model_selection": selected_models,
                "files_created": created_files,
                "files_edited": edited_files,
                "commands": [result.model_dump() for result in command_results],
                "estimated_cost_usd": metrics.total_estimated_cost_usd,
            },
            timeline=[event.model_dump() for event in events],
            commands=[result.model_dump() for result in command_results],
            project_manifest=project_manifest,
        )
        workspace_summary = WorkspaceSummary(
            root=project_manager.public_root(active_project_id),
            files_created=created_files,
            files_edited=edited_files,
            commands_run=command_results,
            command_success=command_success,
        )
        project_workspace_summary = ProjectWorkspaceSummary(
            project_id=active_project_id,
            root=project_workspace.root,
            files_created=created_files,
            files_edited=edited_files,
            commands_run=[result.model_dump() for result in command_results],
            command_success=command_success,
        )
        agent_infos = []
        if research_context:
            agent_infos.append(
                AgentInfo(
                    name="Research Agent",
                    role="Research and source collection",
                    assigned_model=research_model,
                    status="completed",
                    latest_action="Prepared research context",
                    completed_work=["Created research_brief.md", "Created research_sources.json"],
                )
            )
        agent_infos.extend(
            [
                AgentInfo(
                    name="Real Coding Agent" if real_coding_result and real_coding_result.used and not real_coding_result.hardcoded_fallback_used else "Website Agent",
                    role="Reusable coding/file editing" if real_coding_result and real_coding_result.used and not real_coding_result.hardcoded_fallback_used else "Template fallback for website project files",
                    assigned_model=(real_coding_result.selected_model if real_coding_result else website_model),
                    status="blocked" if real_coding_result and real_coding_result.parse_error else "completed",
                    latest_action="Applied real coding patch" if real_coding_result and real_coding_result.patch_applied else ("Prepared dry-run patch" if real_coding_result and real_coding_result.dry_run else "Rejected invalid provider patch" if real_coding_result and real_coding_result.parse_error else "Updated website files"),
                    completed_work=(real_coding_result.files_changed if real_coding_result else created_files + edited_files),
                ),
                AgentInfo(name="QA Agent", role="Review and quality control", assigned_model=qa_model, status="completed", latest_action="Reviewed website update", completed_work=["Reviewed file changes and command logs."]),
            ]
        )
        record = RunRecord(
            run_id=run_id,
            command=command,
            mode=mode,
            project_id=active_project_id,
            run_type="website_update",
            status=run_status,
            started_at=started_at,
            completed_at=completed_at,
            events=events,
            agents=agent_infos,
            task_graph=build_default_task_graph(),
            metrics=metrics,
            memory=memory,
            final_output=FinalOutput(
                summary=f"Real Coding Agent v1 workflow completed for project {active_project_id}.",
                what_was_done=[
                    "Selected workflow: website_update.",
                    self._real_coding_final_action(real_coding_result),
                    f"Actual provider: {real_coding_result.actual_provider if real_coding_result else 'n/a'}.",
                    f"Selected coding model: {real_coding_result.selected_model if real_coding_result else 'n/a'}.",
                    f"Prompt file scope: {real_coding_result.allowed_user_file_scope.scope_type if real_coding_result else 'n/a'}.",
                    self._real_coding_qa_report_line(real_coding_result),
                    "Logged model selection reasons and Real Coding Agent behavior.",
                ],
                recommended_next_actions=["Review files in Project Workspace.", "Run the site locally before any public use."],
                generated_artifacts=[artifact.name for artifact in artifact_records],
            ),
            artifacts=artifact_records,
            workspace=workspace_summary,
            project_workspace=project_workspace_summary,
            models_used=sorted({event.model_used for event in events}),
            project_files_created=created_files,
            project_files_updated=edited_files,
            commands_run=[result.model_dump() for result in command_results],
            usage_summary={
                "estimated_cost_usd": metrics.total_estimated_cost_usd,
                "estimated_tokens": metrics.total_estimated_tokens,
                "agents_used": metrics.agents_used,
                "models_used": sorted({event.model_used for event in events}),
                "selected_workflow": agent_plan.selected_workflow,
                "search_needed": agent_plan.search_needed,
                "search_unavailable": agent_plan.search_unavailable,
                "search_provider_id": (agent_plan.selected_search_provider or {}).get("id") if isinstance(agent_plan.selected_search_provider, dict) else None,
                "user_file_changes": [*created_files, *edited_files],
                "system_metadata_files": ["project_state.md", "manifest.json"],
                "real_coding_agent": real_coding_result.model_dump() if real_coding_result else {},
                "project_sanity_validation": {
                    "safe_commands_executed": len(command_results),
                    "commands": [result.model_dump() for result in command_results],
                    "result": "not_run" if not command_results else ("passed" if command_success else "needs_review"),
                    "reason": "General project sanity validation. py_compile checks website/app.py syntax and does not directly validate unchanged HTML/JSON copy.",
                },
            },
            memory_updates=[],
            agent_plan=agent_plan.model_dump(),
            model_selection=selected_models,
        )
        return self._finalize_run(record)

    async def _execute_prototype_build(
        self,
        *,
        command: str,
        mode: str,
        project_id: str | None,
        run_type: str,
        allow_ceo_live: bool,
        allow_file_writes: bool,
        allow_safe_commands: bool,
        allow_web_search: bool,
        max_cost: float,
        run_id: str,
        started_at: datetime,
        memory,
    ) -> RunRecord:
        if not allow_file_writes:
            raise HTTPException(status_code=403, detail=f"{run_type} requires allow_file_writes=true.")

        active_project_id = project_id or "default-project"
        project_manager = ProjectWorkspaceManager(self.settings)
        project_workspace = project_manager.ensure_project_workspace(active_project_id)
        project_root = project_manager.get_project_root(active_project_id)
        project_manager.create_run_log_folder(run_id)
        project_manifest = project_manager.get_project_manifest(active_project_id)
        project_state_text = project_manager.read_project_file(active_project_id, "project_state.md")
        relevant_project_files = [
            item.model_dump()
            for item in project_manifest.files
            if item.path.startswith("website/") or item.path in {"project_state.md", "manifest.json"}
        ][:8]
        command_runner = SafeCommandRunner(self.settings)
        agents = {
            **self._build_agents(allow_ceo_live=allow_ceo_live, mode=mode),
            "file_builder": FileBuilderAgent("File Builder Agent", "Creates safe workspace files", self.settings.cheap_worker_model),
        }
        relevant_memory = [snippet.content for snippet in memory.retrieved_snippets[:2]]
        task_packets: list[TaskPacket] = []
        events: list[RunEvent] = []
        artifact_records = []
        agent_plan = self._plan_run(
            command=command,
            run_type=run_type,
            project_id=active_project_id,
            mode=mode,
            allow_file_writes=allow_file_writes,
            allow_safe_commands=allow_safe_commands,
            allow_web_search=allow_web_search,
            max_cost=max_cost,
        )
        selected_models = self._selection_by_agent(agent_plan)
        website_only = agent_plan.selected_workflow == "website_update"

        def packet(task_id: str, agent_key: str, objective: str, input_artifacts: list[str], expected_outputs: list[str], allowed_tools: list[str]) -> TaskPacket:
            agent = agents[agent_key]
            item = TaskPacket(
                run_id=run_id,
                project_id=active_project_id,
                task_id=task_id,
                agent_name=agent.name,
                agent_role=agent.role,
                objective=objective,
                relevant_memory=relevant_memory,
                relevant_project_files=[
                    {"path": "project_state.md", "summary": project_state_text[:800]},
                    *relevant_project_files,
                ],
                input_artifacts=input_artifacts,
                expected_outputs=expected_outputs,
                constraints=[
                    "Do not use web search or external APIs.",
                    "Do not touch environment files or secrets.",
                    "Only write inside the persistent project workspace.",
                    "Keep run logs separate from project files.",
                    "Use artifacts for handoff between agents.",
                ],
                allowed_tools=allowed_tools,
            )
            task_packets.append(item)
            return item

        ceo_packet = packet("task-ceo-plan", "ceo", "Plan the prototype build and define safe handoffs.", [], ["ceo_plan.md"], ["artifact_write"])
        ceo_output = await self._run_step(
            run_id=run_id,
            command=command,
            mode=mode,
            agent_name="CEO Agent",
            agent_role=agents["ceo"].role,
            model=agents["ceo"].assigned_model,
            request_type="planning",
            prompt=ceo_packet.model_dump_json(indent=2),
            mock_output=self._ceo_plan(command),
        )
        ceo_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="ceo_plan.md",
            artifact_type="markdown",
            content=ceo_output["text"],
            agent_name="CEO Agent",
            summary="CEO plan for sandboxed prototype build.",
        )
        artifact_records.append(ceo_artifact)
        events.append(self._event_from_step(ceo_output, "Created CEO prototype plan", ceo_packet.objective, ceo_artifact.id))

        model_selection = self._model_selection(agents, mode, allow_ceo_live)
        selector_packet = packet("task-model-selection", "selector", "Select safe models and tools for prototype build.", [ceo_artifact.id], ["model_selection.json"], ["artifact_write"])
        selector_output = await self._run_step(
            run_id=run_id,
            command=command,
            mode=mode,
            agent_name="Model Selector Agent",
            agent_role=agents["selector"].role,
            model=agents["selector"].assigned_model,
            request_type="model_routing",
            prompt=selector_packet.model_dump_json(indent=2),
            mock_output=json.dumps(model_selection, indent=2),
        )
        selector_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="model_selection.json",
            artifact_type="json",
            content=selector_output["text"],
            agent_name="Model Selector Agent",
            summary="Safe model choices for prototype build.",
        )
        artifact_records.append(selector_artifact)
        events.append(self._event_from_step(selector_output, "Selected models and workspace tools", selector_packet.objective, selector_artifact.id))

        operations_packet = packet("task-operations", "operations", "Define order flow and manual approval requirements for the prototype.", [ceo_artifact.id], ["operations_checklist.md"], ["artifact_write"])
        operations_output = await self._run_step(
            run_id=run_id,
            command=command,
            mode=mode,
            agent_name="Operations Agent",
            agent_role=agents["operations"].role,
            model=agents["operations"].assigned_model,
            request_type="operations_planning",
            prompt=operations_packet.model_dump_json(indent=2),
            mock_output=agents["operations"].create_operations_checklist(command),
        )
        operations_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="operations_checklist.md",
            artifact_type="markdown",
            content=operations_output["text"],
            agent_name="Operations Agent",
            summary="Operations and manual approval requirements for prototype.",
        )
        artifact_records.append(operations_artifact)
        events.append(self._event_from_step(operations_output, "Created prototype operations checklist", operations_packet.objective, operations_artifact.id))

        content_packet = packet("task-content", "content", "Write homepage and product content for the prototype.", [ceo_artifact.id, operations_artifact.id], ["content_calendar.md"], ["artifact_write"])
        content_output = await self._run_step(
            run_id=run_id,
            command=command,
            mode=mode,
            agent_name="Content Agent",
            agent_role=agents["content"].role,
            model=agents["content"].assigned_model,
            request_type="content_generation",
            prompt=content_packet.model_dump_json(indent=2),
            mock_output=agents["content"].create_content_calendar(command),
        )
        content_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="content_calendar.md",
            artifact_type="markdown",
            content=content_output["text"],
            agent_name="Content Agent",
            summary="Prototype copy and launch content context.",
        )
        artifact_records.append(content_artifact)
        events.append(self._event_from_step(content_output, "Created content inputs for prototype", content_packet.objective, content_artifact.id))

        builder_packet = packet(
            "task-file-builder",
            "file_builder",
            "Create or continue the Greek yogurt order website files inside the persistent project workspace.",
            [ceo_artifact.id, operations_artifact.id, content_artifact.id],
            ["README.md", "app.py", "requirements.txt", "sample_orders.json", "index.html"],
            ["project_file_write"],
        )
        file_parse_note = ""
        if mode == "live":
            builder_context = AgentExecutionContext(
                run_id=run_id,
                project_id=active_project_id,
                mode=mode,
                agent_name="File Builder Agent",
                agent_role=agents["file_builder"].role,
                command=command,
                task_objective=builder_packet.objective,
                relevant_memory=relevant_memory,
                relevant_project_files=builder_packet.relevant_project_files,
                input_artifacts=[artifact.model_dump() for artifact in [ceo_artifact, operations_artifact, content_artifact]],
                constraints=builder_packet.constraints,
                allowed_tools=["project_file_write"],
                model=agents["file_builder"].assigned_model,
                provider=get_model_metadata(agents["file_builder"].assigned_model).provider,
                max_output_tokens=min(500, self.settings.max_output_tokens_per_call),
                max_cost_usd=self.settings.max_cost_per_call_usd,
            )
            builder_llm_output = await run_llm_agent(
                builder_context,
                "You convert approved prototype requirements into safe project file actions.",
                (
                    "Return JSON only with this shape: "
                    '{"file_actions":[{"operation":"create|update","path":"website/app.py","summary":"...","content":"..."}]}. '
                    "Allowed paths must stay under website/, content/, or docs/ and use safe extensions. "
                    f"Command: {command}"
                ),
                settings=self.settings,
                usage_store=self.usage,
                request_type="file_generation",
            )
            file_entries, file_parse_note = self._apply_live_file_actions(
                active_project_id,
                run_id,
                builder_llm_output.output_text,
                "File Builder Agent",
            )
            if not file_entries:
                file_parse_note = file_parse_note or "No valid file actions returned; deterministic safe builder fallback was used."
                file_entries = agents["file_builder"].build_project_greek_yogurt_site(active_project_id, run_id, command)
        else:
            file_entries = agents["file_builder"].build_project_greek_yogurt_site(active_project_id, run_id, command)
        workspace_artifacts = []
        for entry in file_entries:
            artifact = self.artifacts.register_file(
                run_id=run_id,
                name=entry.path,
                artifact_type="project_file",
                path=str(project_root / entry.path),
                agent_name="File Builder Agent",
                summary=entry.after_summary,
            )
            workspace_artifacts.append(artifact)
            artifact_records.append(artifact)
        file_builder_text = "\n".join(f"- {entry.operation}: {entry.path} ({entry.size_bytes} bytes)" for entry in file_entries)
        if file_parse_note:
            file_builder_text = f"{file_builder_text}\n\nLive file action note: {file_parse_note}"
        file_builder_event = self._manual_step(
            run_id=run_id,
            mode=mode,
            agent_name="File Builder Agent",
            agent_role=agents["file_builder"].role,
            model=agents["file_builder"].assigned_model,
            request_type="file_generation",
            input_text=builder_packet.model_dump_json(indent=2),
            output_text=file_builder_text,
            action_summary="Created prototype workspace files",
            artifact_id=workspace_artifacts[0].id if workspace_artifacts else ceo_artifact.id,
        )
        events.append(file_builder_event)

        command_results: list[CommandResult] = []
        if allow_safe_commands:
            command_results.append(
                command_runner.run_project_command(
                    active_project_id,
                    run_id,
                    ["python", "-m", "py_compile", "website/app.py"],
                )
            )
        else:
            command_results.append(
                CommandResult(
                    command=["python", "-m", "py_compile", "website/app.py"],
                    cwd=".",
                    exit_code=-1,
                    stdout="",
                    stderr="",
                    duration_ms=0,
                    allowed=False,
                    blocked_reason="allow_safe_commands=false",
                )
            )
        command_text = "\n".join(
            f"- {'allowed' if result.allowed else 'blocked'} {result.command}: exit={result.exit_code} reason={result.blocked_reason or 'n/a'}"
            for result in command_results
        )
        command_event = self._manual_step(
            run_id=run_id,
            mode=mode,
            agent_name="Safe Command Runner",
            agent_role="Validation sandbox",
            model=self.settings.cheap_worker_model,
            request_type="command_validation",
            input_text="Validate generated prototype files with safe commands.",
            output_text=command_text,
            action_summary="Validated generated code with safe command runner",
            artifact_id=workspace_artifacts[0].id if workspace_artifacts else ceo_artifact.id,
        )
        command_event.status = _command_event_status(command_results)  # type: ignore[assignment]
        command_event.action_summary = "Safe command validation failed" if command_event.status == "validation_failed" else command_event.action_summary
        events.append(command_event)

        project_manifest = project_manager.get_project_manifest(active_project_id)
        manifest_artifact = self.artifacts.register_file(
            run_id=run_id,
            name="project_manifest.json",
            artifact_type="project_manifest",
            path=str(project_root / "manifest.json"),
            agent_name="Project Workspace Manager",
            summary="Persistent project manifest with created/updated files.",
        )
        state_artifact = self.artifacts.register_file(
            run_id=run_id,
            name="project_state.md",
            artifact_type="project_state",
            path=str(project_root / "project_state.md"),
            agent_name="Project Workspace Manager",
            summary="Persistent project state before final update.",
        )
        command_log_artifact = self.artifacts.register_file(
            run_id=run_id,
            name="commands.json",
            artifact_type="command_log",
            path=str(self.settings.run_path / run_id / "commands.json"),
            agent_name="Safe Command Runner",
            summary="Safe command execution log.",
        )
        prototype_artifact = self.artifacts.register_file(
            run_id=run_id,
            name="website",
            artifact_type="prototype_project",
            path=str(project_root / "website"),
            agent_name="File Builder Agent",
            summary="Persistent Greek yogurt order website prototype project.",
        )
        artifact_records.extend([manifest_artifact, state_artifact, command_log_artifact, prototype_artifact])

        qa_input = "\n".join([artifact.summary for artifact in artifact_records]) + "\n" + command_text
        qa_packet = packet("task-qa", "qa", "Review generated files, command results, and safety constraints.", [artifact.id for artifact in artifact_records], ["qa_review.md"], ["artifact_write"])
        qa_output = await self._run_step(
            run_id=run_id,
            command=command,
            mode=mode,
            agent_name="QA Agent",
            agent_role=agents["qa"].role,
            model=agents["qa"].assigned_model,
            request_type="validation",
            prompt=qa_packet.model_dump_json(indent=2),
            mock_output=self._prototype_qa_review(command, qa_input, command_results, file_changes_count=len(file_entries)),
        )
        qa_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="qa_review.md",
            artifact_type="markdown",
            content=qa_output["text"],
            agent_name="QA Agent",
            summary="QA review of generated workspace files and command validation.",
        )
        artifact_records.append(qa_artifact)
        events.append(self._event_from_step(qa_output, "Reviewed prototype workspace outputs", qa_packet.objective, qa_artifact.id))

        final_report = self._prototype_final_report(command, active_project_id, file_entries, command_results, artifact_records, task_packets)
        final_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="final_report.md",
            artifact_type="markdown",
            content=final_report,
            agent_name="TheHiveMind",
            summary="Final report for sandboxed autonomy prototype build.",
        )
        artifact_records.append(final_artifact)
        events.append(
            self._manual_step(
                run_id=run_id,
                mode=mode,
                agent_name="TheHiveMind",
                agent_role="Final assembly",
                model=self._safe_ceo_model(mode, allow_ceo_live),
                request_type="final_assembly",
                input_text=qa_output["text"],
                output_text=final_report,
                action_summary="Assembled sandboxed autonomy final report",
                artifact_id=final_artifact.id,
            )
        )

        completed_at = datetime.now(UTC)
        metrics = RunMetrics(
            total_estimated_tokens=sum(event.estimated_tokens or event.estimated_input_tokens + event.estimated_output_tokens for event in events),
            total_estimated_cost_usd=round(sum(event.estimated_cost_usd for event in events), 6),
            agents_used=len({event.agent_name for event in events if event.agent_name != "TheHiveMind"}),
            tasks_completed=len(events),
            run_duration_seconds=round((completed_at - started_at).total_seconds(), 3),
            memory_chunks_retrieved=len(memory.retrieved_snippets),
        )
        assert_run_budget(metrics.total_estimated_cost_usd)
        if metrics.total_estimated_cost_usd > max_cost:
            raise HTTPException(status_code=400, detail=f"Estimated run cost ${metrics.total_estimated_cost_usd:.6f} exceeds request max_cost_usd=${max_cost:.2f}.")

        created_files = [entry.path for entry in file_entries if entry.operation == "created"]
        edited_files = [entry.path for entry in file_entries if entry.operation == "updated"]
        command_success = all(result.allowed and result.exit_code == 0 for result in command_results)
        project_state_content = update_project_state(
            project_root / "project_state.md",
            project_id=active_project_id,
            run_id=run_id,
            command=command,
            files_created=created_files,
            files_edited=edited_files,
            command_success=command_success,
            next_steps=[
                "Review the website prototype locally.",
                "Add tests before expanding beyond a proof of concept.",
                "Keep public claims and launch actions behind human approval.",
            ],
        )
        state_entry = project_manager.write_project_file(
            active_project_id,
            "project_state.md",
            project_state_content,
            "Project Workspace Manager",
            run_id,
            "Latest truth file for the persistent project workspace.",
        )
        project_manifest = project_manager.append_project_run(
            active_project_id,
            run_id,
            f"Prototype build run completed for: {command}",
        )
        project_manager.write_run_logs(
            run_id=run_id,
            run_summary={
                "run_id": run_id,
                "project_id": active_project_id,
                "run_type": run_type,
                "status": "completed",
                "files_created": created_files,
                "files_edited": edited_files,
                "commands": [result.model_dump() for result in command_results],
                "artifact_ids": [artifact.id for artifact in artifact_records],
                "estimated_cost_usd": metrics.total_estimated_cost_usd,
            },
            timeline=[event.model_dump() for event in events],
            commands=[result.model_dump() for result in command_results],
            project_manifest=project_manifest,
        )
        workspace_summary = WorkspaceSummary(
            root=project_manager.public_root(active_project_id),
            files_created=created_files,
            files_edited=[*edited_files, state_entry.path] if state_entry.operation == "updated" else edited_files,
            commands_run=command_results,
            command_success=command_success,
        )
        project_workspace_summary = ProjectWorkspaceSummary(
            project_id=active_project_id,
            root=project_workspace.root,
            files_created=[entry.path for entry in file_entries if entry.operation == "created"],
            files_edited=[entry.path for entry in file_entries if entry.operation == "updated"],
            commands_run=[result.model_dump() for result in command_results],
            command_success=command_success,
        )
        memory_updates = self._update_prototype_memory(
            run_id=run_id,
            project_id=active_project_id,
            run_type=run_type,
            command=command,
            file_entries=[*file_entries, state_entry],
            command_results=command_results,
            artifact_records=artifact_records,
            task_packets=task_packets,
            cost=metrics.total_estimated_cost_usd,
        )
        record = RunRecord(
            run_id=run_id,
            command=command,
            mode=mode,
            project_id=active_project_id,
            run_type=run_type,
            status="completed",
            started_at=started_at,
            completed_at=completed_at,
            events=events,
            agents=[self._agent_info(agent) for agent in agents.values()],
            task_graph=build_default_task_graph(),
            metrics=metrics,
            memory=memory,
            final_output=FinalOutput(
                summary=f"Persistent Project Workspace v1 updated project {active_project_id} for: {command}",
                what_was_done=[
                    "Created task packets with task-specific context.",
                    "Generated or updated real files inside the persistent project workspace.",
                    "Saved run-specific logs separately from project files.",
                    "Ran safe validation commands and logged results.",
                    "Registered generated files, project manifest, project state, and command logs as artifacts.",
                    "Updated memory with summaries, paths, command results, and agent decisions.",
                ],
                recommended_next_actions=[
                    "Open the project files for review before running the prototype server manually.",
                    "Add tests if the prototype becomes more than a static proof of concept.",
                    "Keep dangerous commands and external actions blocked until explicit approval flows exist.",
                ],
                generated_artifacts=[artifact.name for artifact in artifact_records],
            ),
            artifacts=artifact_records,
            workspace=workspace_summary,
            project_workspace=project_workspace_summary,
            models_used=sorted({event.model_used for event in events}),
            project_files_created=created_files,
            project_files_updated=[*edited_files, state_entry.path] if state_entry.operation == "updated" else edited_files,
            commands_run=[result.model_dump() for result in command_results],
            usage_summary={
                "estimated_cost_usd": metrics.total_estimated_cost_usd,
                "estimated_tokens": metrics.total_estimated_tokens,
                "agents_used": metrics.agents_used,
                "models_used": sorted({event.model_used for event in events}),
                "selected_workflow": agent_plan.selected_workflow,
            },
            memory_updates=memory_updates,
            agent_plan=agent_plan.model_dump(),
            model_selection=selected_models,
        )
        return self._finalize_run(record)

    def _finalize_run(self, record: RunRecord) -> RunRecord:
        self._apply_memory_control_summary(record)
        self._save_run(record)
        if self.settings.memory_ingest_after_run:
            result = MemoryIngestor(self.settings).ingest_record(record)
            memory_ids = result.get("memory_ids", [])
            if memory_ids:
                record.memory_updates = [*record.memory_updates, *memory_ids]
                self._apply_memory_control_summary(record)
                self._save_run(record)
        return record

    def _apply_memory_control_summary(self, record: RunRecord) -> None:
        use_memory = bool(getattr(self, "_use_memory_for_current_run", True))
        record.usage_summary["memory_control"] = {
            "use_memory": use_memory,
            "retrieval_enabled": use_memory,
            "retrieved_count": len(record.memory.retrieved_snippets),
            "ingestion_after_run_enabled": self.settings.memory_ingest_after_run,
            "ingested_after_run_count": len(record.memory_updates),
            "ingestion_note": "Memory ingestion stores this run for future runs; it does not mean retrieved memory was used in this run.",
        }

    def _build_agents(self, *, allow_ceo_live: bool, mode: str) -> dict[str, Any]:
        return {
            "ceo": CEOAgent("CEO Agent", "Planner and delegator", self._safe_ceo_model(mode, allow_ceo_live)),
            "selector": ModelSelectorAgent("Model Selector Agent", "Routes tasks to models", self.settings.model_selector_model),
            "research": BusinessAgent("Research Agent", "Market research and local assumptions", self.settings.cheap_search_worker_model),
            "content": BusinessAgent("Content Agent", "Launch content and positioning", self.settings.cheap_worker_model),
            "operations": OperationsAgent("Operations Agent", "Order flow and manual operations", self.settings.cheap_worker_model),
            "qa": QAAgent("QA Agent", "Review and quality control", self.settings.cheap_worker_model),
        }

    def _safe_ceo_model(self, mode: str, allow_ceo_live: bool) -> str:
        if mode == "live" and not allow_ceo_live:
            return self.settings.ceo_fallback_model
        return self.settings.ceo_model

    async def _run_step(
        self,
        *,
        run_id: str,
        mode: str,
        command: str,
        agent_name: str,
        agent_role: str,
        model: str,
        request_type: str,
        prompt: str,
        mock_output: str,
    ) -> dict[str, Any]:
        metadata = get_model_metadata(model, self.settings.ceo_service_tier if model == self.settings.ceo_model else None)
        memory_context = ""
        if getattr(self, "_use_memory_for_current_run", True) and self.settings.enable_vector_memory and ((mode == "mock" and self.settings.memory_use_in_mock) or (mode == "live" and self.settings.memory_use_in_live)):
            packet = build_context_packet(
                agent_id=_agent_id_from_name(agent_name),
                project_id=None,
                run_id=run_id,
                run_type=request_type,
                task=request_type,
                current_command=command,
                settings=self.settings,
            )
            memory_context = format_context_packet(packet)
        prompt_with_memory = f"{memory_context}\n\n{prompt}" if memory_context else prompt
        context = AgentExecutionContext(
            run_id=run_id,
            project_id="unassigned",
            mode=mode,
            agent_name=agent_name,
            agent_role=agent_role,
            command=command,
            task_objective=request_type,
            relevant_memory=[memory_context] if memory_context else [],
            relevant_project_files=[],
            input_artifacts=[],
            constraints=["Do not browse the web.", "Do not expose secrets.", "Do not perform external actions."],
            allowed_tools=["artifact_write"],
            model=model,
            provider=metadata.provider,
            max_output_tokens=min(500, self.settings.max_output_tokens_per_call),
            max_cost_usd=self.settings.max_cost_per_call_usd,
        )
        if mode == "mock":
            input_tokens = estimate_tokens(prompt_with_memory)
            output_tokens = estimate_tokens(mock_output)
            cost = estimate_cost_usd(model, input_tokens, output_tokens)
            self.usage.log_call(
                run_id=run_id,
                task_id=f"{run_id}:{request_type}",
                agent_name=agent_name,
                agent_role=agent_role,
                provider=metadata.provider,
                model=model,
                mode=mode,
                request_type=request_type,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=cost,
                latency_ms=1,
                success=True,
                metadata={"usage_source": "run_engine_v1"},
            )
            output_text = mock_output
            latency_ms = 1
        else:
            output = await run_llm_agent(
                context,
                "You are an agent inside TheHiveMind. Produce concise, structured, safe output.",
                prompt_with_memory,
                settings=self.settings,
                usage_store=self.usage,
                request_type=request_type,
            )
            input_tokens = output.input_tokens
            output_tokens = output.output_tokens
            cost = output.estimated_cost_usd
            output_text = output.output_text
            latency_ms = output.latency_ms
        return {
            "run_id": run_id,
            "agent_name": agent_name,
            "agent_role": agent_role,
            "provider": metadata.provider,
            "model": model,
            "request_type": request_type,
            "input": prompt_with_memory,
            "text": output_text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
            "latency_ms": latency_ms,
        }

    def _event_from_step(self, step: dict[str, Any], action_summary: str, input_summary: str, artifact_id: str | None) -> RunEvent:
        return RunEvent(
            timestamp=datetime.now(UTC),
            run_id=step["run_id"],
            agent_name=step["agent_name"],
            agent_role=step["agent_role"],
            status="completed",
            action_summary=action_summary,
            input_summary=input_summary,
            output_summary=step["text"],
            model_used=step["model"],
            provider=step["provider"],
            estimated_input_tokens=step["input_tokens"],
            estimated_output_tokens=step["output_tokens"],
            estimated_tokens=step["input_tokens"] + step["output_tokens"],
            estimated_cost_usd=step["cost"],
            estimated_cost=step["cost"],
            artifact_id=artifact_id,
        )

    def _manual_step(
        self,
        *,
        run_id: str,
        mode: str,
        agent_name: str,
        agent_role: str,
        model: str,
        request_type: str,
        input_text: str,
        output_text: str,
        action_summary: str,
        artifact_id: str,
    ) -> RunEvent:
        metadata = get_model_metadata(model, self.settings.ceo_service_tier if model == self.settings.ceo_model else None)
        input_tokens = estimate_tokens(input_text)
        output_tokens = estimate_tokens(output_text)
        cost = estimate_cost_usd(model, input_tokens, output_tokens)
        self.usage.log_call(
            run_id=run_id,
            task_id=f"{run_id}:{request_type}",
            agent_name=agent_name,
            agent_role=agent_role,
            provider=metadata.provider,
            model=model,
            mode=mode,
            request_type=request_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
            latency_ms=1,
            success=True,
            metadata={"usage_source": "run_engine_v1"},
        )
        return RunEvent(
            timestamp=datetime.now(UTC),
            run_id=run_id,
            agent_name=agent_name,
            agent_role=agent_role,
            status="completed",
            action_summary=action_summary,
            input_summary=input_text,
            output_summary=output_text,
            model_used=model,
            provider=metadata.provider,
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=output_tokens,
            estimated_tokens=input_tokens + output_tokens,
            estimated_cost_usd=cost,
            estimated_cost=cost,
            artifact_id=artifact_id,
        )

    def _ceo_prompt(self, command: str, current_state: str) -> str:
        return f"Create a controlled plan for this command. Current state: {current_state}\nCommand: {command}"

    def _ceo_plan(self, command: str) -> str:
        return f"""# CEO Plan

## Goal Understanding
Create a controlled launch plan for: {command}

## Scope
- Include market assumptions, positioning, content, order flow, and QA.
- Exclude supplier sourcing and physical yogurt production.
- Keep execution sequential and human-approved.

## Task Breakdown
- Research Agent: market assumptions and verification questions.
- Content Agent: positioning and 14-day social content calendar.
- Operations Agent: WhatsApp/order handling and manual workflows.
- QA Agent: practicality, hallucination, and approval review.

## Success Criteria
- Saved artifacts exist for every stage.
- Usage is logged by provider, model, agent, and token count.
- No external APIs are called in mock mode.
- Human approval points are explicit.

## Risk Areas
- Unverified health, nutrition, halal, delivery, and regulatory claims.
- Cold-chain and delivery feasibility.
- Pricing assumptions and local competitor data.
"""

    def _model_selection(self, agents: dict[str, Any], mode: str, allow_ceo_live: bool) -> dict[str, Any]:
        return {
            "mode": mode,
            "allow_ceo_live": allow_ceo_live,
            "models": {
                key: {
                    "agent_name": agent.name,
                    "model": agent.assigned_model,
                    "provider": get_model_metadata(agent.assigned_model).provider,
                    "reason": "Selected for this controlled v1 role with low-cost defaults where possible.",
                }
                for key, agent in agents.items()
            },
            "safety": {
                "web_search_enabled": False,
                "live_calls_allowed": self.settings.is_live_allowed(),
                "ceo_live_policy": "CEO model is downgraded to cheap worker in live mode unless allow_ceo_live=true.",
            },
        }

    def _qa_review(self, command: str, artifacts: list[str]) -> str:
        return f"""# QA Review

## Command Reviewed
{command}

## Hallucination Check
- No live web claims were introduced.
- Competitor and market references are placeholders or assumptions.
- Nutrition, halal, legal, and delivery claims are marked for human verification.

## Missing Assumptions
- Exact city, launch budget, price points, cup sizes, and delivery radius.
- Food registration and labeling requirements.
- Visual identity and actual product photography.

## Practicality Check
- WhatsApp-first order flow is practical for a founder batch.
- Manual approval checkpoints reduce operational risk.
- Content calendar is usable but needs real product images and final pricing.

## Human Approval Required
- Health/nutrition wording.
- Legal/compliance claims.
- Delivery promise and refund policy.
- Any public launch announcement.

## Status
Approved for internal planning only. Not approved for public claims or live launch without human review.
"""

    def _final_report(self, command: str, project_id: str | None, artifacts: list[Any], steps: list[dict[str, Any]]) -> str:
        cost = round(sum(step["cost"] for step in steps), 6)
        tokens = sum(step["input_tokens"] + step["output_tokens"] for step in steps)
        artifact_list = "\n".join(f"- {artifact.name}: {artifact.summary}" for artifact in artifacts)
        return f"""# Final Report

## Command
{command}

## Project
{project_id or "unassigned"}

## Summary
Run Engine v1 completed a controlled, sequential workflow and saved stage outputs as artifacts. This run is suitable for internal planning and review, not autonomous execution.

## Usage Summary
- Estimated model spend: ${cost:.6f}
- Estimated tokens: {tokens}
- Search/grounding calls: 0
- Live external actions: none

## Artifacts
{artifact_list}

## Approval Notes
- No emails, social posts, deployments, supplier sourcing, or physical production steps were executed.
- Human review is required before using claims, prices, delivery promises, or launch content publicly.
"""

    def _apply_live_file_actions(self, project_id: str, run_id: str, output_text: str, agent_name: str) -> tuple[list[Any], str]:
        try:
            cleaned = output_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                if cleaned.lower().startswith("json"):
                    cleaned = cleaned[4:].strip()
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            return [], "File Builder returned invalid JSON; no LLM file actions were applied."
        actions = payload.get("file_actions", []) if isinstance(payload, dict) else []
        if not isinstance(actions, list):
            return [], "File Builder JSON did not contain a valid file_actions list."
        manager = ProjectWorkspaceManager(self.settings)
        entries = []
        rejected = []
        for action in actions:
            if not isinstance(action, dict):
                rejected.append("non-object action")
                continue
            path = str(action.get("path", ""))
            content = action.get("content")
            summary = str(action.get("summary", f"Live file action for {path}"))
            if not path or not isinstance(content, str):
                rejected.append(path or "missing path")
                continue
            try:
                entries.append(manager.write_project_file(project_id, path, content, agent_name, run_id, summary))
            except HTTPException as exc:
                rejected.append(f"{path}: {exc.detail}")
        note = f"Rejected file actions: {', '.join(rejected)}" if rejected else ""
        return entries, note

    def _prototype_qa_review(
        self,
        command: str,
        qa_input: str,
        command_results: list[CommandResult],
        *,
        file_changes_count: int = 1,
        search_result: SearchResultPayload | None = None,
        memory_packet: Any | None = None,
        changed_paths: list[str] | None = None,
        system_metadata_paths: list[str] | None = None,
        homepage_copy_scope: bool = False,
        allowed_user_file_scope: dict[str, Any] | None = None,
        workflow: str = "prototype_build",
        real_coding_result: RealCodingAgentResult | None = None,
    ) -> str:
        command_status = "passed" if all(result.allowed and result.exit_code == 0 for result in command_results) else "needs review"
        user_changed_paths = changed_paths or []
        metadata_paths = system_metadata_paths or []
        scope_lines = []
        if allowed_user_file_scope and allowed_user_file_scope.get("allowed_user_files"):
            allowed = set(allowed_user_file_scope.get("allowed_user_files") or [])
            violations = [path for path in user_changed_paths if path not in allowed]
            if violations:
                scope_lines.append(f"- File-scope failure: unauthorized user-facing files changed: {', '.join(violations)}.")
            else:
                scope_lines.append(f"- User-facing file changes matched prompt scope: {allowed_user_file_scope.get('scope_type')}.")
                scope_lines.append(f"- Scope reason: {allowed_user_file_scope.get('reason')}.")
        elif homepage_copy_scope:
            allowed = {"website/templates/index.html", "website/data/faqs.json", "website/README.md"}
            violations = [path for path in user_changed_paths if path not in allowed]
            if violations:
                scope_lines.append(f"- File-scope warning: unrelated user-facing files changed: {', '.join(violations)}.")
            else:
                scope_lines.append("- User-facing file changes were limited to approved website scope.")
                scope_lines.append("- Copy-only task did not modify backend/app code, dependencies, order data, or status data.")
        elif user_changed_paths and all(path.startswith("website/") for path in user_changed_paths):
            scope_lines.append("- User-facing file changes were limited to website/.")
        if metadata_paths:
            scope_lines.append(f"- System metadata was updated separately: {', '.join(metadata_paths)}.")
        if workflow == "website_update":
            title = "Website Update QA Review"
            workflow_line = "Workflow: website_update"
            file_review = self._website_update_qa_file_review(real_coding_result, file_changes_count)
        elif workflow == "research_only":
            title = "Research QA Review"
            workflow_line = "Workflow: research_only"
            file_review = "- No user-facing project files were updated because this was a research-only workflow."
        else:
            title = "Prototype QA Review"
            workflow_line = f"Workflow: {workflow}"
            file_review = (
                "- No project files were updated."
                if file_changes_count == 0
                else "- Project files were generated or updated under the persistent project workspace.\n- Generated files include Python, Markdown, JSON, and HTML."
            )
        search_review = self._search_qa_wording(search_result, memory_packet)
        memory_review = self._memory_qa_wording(memory_packet, qa_input)
        validation_reason = ""
        if real_coding_result and not real_coding_result.validation.accepted:
            validation_reason = f"\nReason: {'; '.join(real_coding_result.validation.violations) or 'Patch validation rejected the proposed change.'}\n"
        return f"""# {title}

{workflow_line}

## Command
{command}

## File Review
{file_review}
{validation_reason}
- User-facing file changes reviewed: {file_changes_count}
{chr(10).join(scope_lines) if scope_lines else "- No narrow file-scope rules were triggered."}
- No `.env` files, dependency installs, deployments, emails, or social posts were created.

## Search Review
{search_review}

## Memory Review
{memory_review}

## Command Validation
- Safe command status: {command_status}
- Project sanity commands reviewed: {len(command_results)}
- Note: generic `py_compile website/app.py` checks existing Python syntax and does not directly validate unchanged HTML/JSON copy.

## Safety Review
- File writes were limited to the approved project workspace.
- Validation used the command allowlist.
- Prototype server was not started automatically.

## Handoff Summary
{qa_input[:2000]}

## Status
Approved for local review only. Human approval is still required before public use, deployment, or live customer handling.
"""

    def _website_update_qa_file_review(self, result: RealCodingAgentResult | None, file_changes_count: int) -> str:
        if result and result.patch_applied:
            return "- User-facing file changes were applied within the approved scope."
        if result and result.dry_run:
            return "- No user-facing file changes were applied because dry run was enabled. The proposed patch was validated but not applied."
        if result and not result.validation.accepted:
            if result.live_call_made:
                reason = "; ".join(result.validation.violations) or "The live coding provider output was rejected before patch application."
                return f"- No user-facing file changes were applied because the Real Coding Agent provider response could not be validated.\n- Reason: {reason}"
            return "- No user-facing file changes were applied because the proposed patch was rejected by validation."
        if result and result.no_change_reason:
            return f"- No user-facing file changes were applied because {result.no_change_reason}"
        if file_changes_count == 0:
            return "- No user-facing file changes were applied because the proposed patch resulted in no necessary changes."
        return "- User-facing file changes were applied within the approved scope."

    def _search_qa_wording(self, search_result: SearchResultPayload | None, memory_packet: Any | None = None) -> str:
        if self._memory_has_previous_sources(memory_packet):
            if search_result is None or not search_result.research_used:
                return "- New live search was not used. Previous memory sources from prior runs were used; do not treat memory as fresh search."
        if search_result is None:
            return "- No search or memory sources were used."
        if search_result.error_type:
            if search_result.error_type == "search_unavailable":
                return "- No new live search was run because search was unavailable/skipped. No current claims should be made from this run."
            return f"- Search failed. Use the error message and do not make current claims. Error: {search_result.error_message or search_result.error_type}"
        if search_result.mock_fixture:
            return "- Mock search fixture was used. Do not treat these as real sources."
        if search_result.research_used and search_result.sources:
            return "- Live search was executed and sources were stored. Review source quality before public use."
        return "- Search was skipped/unavailable. No current claims should be made."

    def _search_next_action(self, search_result: SearchResultPayload) -> str:
        if search_result.error_type:
            return "Search was skipped/unavailable. Enable web search to collect current sources."
        if search_result.mock_fixture:
            return "Mock search fixtures were used. Enable live search for current provider data."
        if search_result.research_used:
            return "Live web search was enabled. Review source quality and search cost before using the findings publicly."
        return "Search was skipped/unavailable. Enable web search to collect current sources."

    async def _run_research_search(
        self,
        *,
        command: str,
        mode: str,
        allow_web_search: bool,
        provider_id: str | None,
        run_id: str,
        project_id: str | None,
    ):
        if not allow_web_search or not provider_id:
            SearchLogStore(self.settings).append(
                {
                    "run_id": run_id,
                    "project_id": project_id,
                    "provider_id": provider_id,
                    "mode": mode,
                    "query": command,
                    "status": "skipped",
                    "source_count": 0,
                    "sources": [],
                    "cache_hit": False,
                    "mock_fixture": False,
                    "error_type": "search_unavailable",
                    "error_message": "Web search was disabled or no search provider was selected.",
                    "cost": {"estimated_usd": 0.0, "source": "search_tool_estimate"},
                }
            )
            return SearchResultPayload(
                research_used=False,
                search_provider_id=provider_id,
                brief="Web search was disabled or no search provider was selected.",
                limitations=["No live search call was made."],
                error_type="search_unavailable",
                error_message="Web search was disabled or no search provider was selected.",
            )
        if provider_id == "exa_direct":
            return await run_exa_search(
                SearchRequest(
                    query=command,
                    provider_id=provider_id,
                    max_results=5,
                    mode=mode,
                    allow_web_search=allow_web_search,
                    run_id=run_id,
                    project_id=project_id,
                    agent_name="Research Agent",
                ),
                settings=self.settings,
                store=self.usage_store_for_search(),
            )
        SearchLogStore(self.settings).append(
            {
                "run_id": run_id,
                "project_id": project_id,
                "provider_id": provider_id,
                "mode": mode,
                "query": command,
                "status": "skipped",
                "source_count": 0,
                "sources": [],
                "cache_hit": False,
                "mock_fixture": False,
                "error_type": "provider_not_wired",
                "error_message": "Only Exa Direct is wired for live run-level search calls right now.",
                "cost": {"estimated_usd": 0.0, "source": "search_tool_estimate"},
            }
        )
        return SearchResultPayload(
            research_used=False,
            search_provider_id=provider_id,
            brief=f"{provider_id} is selected but not executed in this path.",
            limitations=["Only Exa Direct is wired for live run-level search calls right now."],
            error_type="provider_not_wired",
            error_message="Only Exa Direct is wired for live run-level search calls right now.",
        )

    def _research_sources_payload(self, agent_plan: dict[str, Any], search_result: SearchResultPayload) -> dict[str, Any]:
        provider_id = search_result.search_provider_id or (
            (agent_plan.get("selected_search_provider") or {}).get("id")
            if isinstance(agent_plan.get("selected_search_provider"), dict)
            else None
        )
        sources = [source.model_dump() for source in search_result.sources]
        return {
            "search_used": bool(search_result.research_used),
            "search_unavailable": bool(agent_plan.get("search_unavailable") or search_result.error_type),
            "provider_id": provider_id,
            "mock_fixture": search_result.mock_fixture,
            "cache_hit": search_result.cache_hit,
            "reason": search_result.error_message or "; ".join(search_result.limitations) or None,
            "error_type": search_result.error_type,
            "error_message": search_result.error_message,
            "source_count": len(sources),
            "cost": search_result.cost,
            "sources": sources,
        }

    def usage_store_for_search(self):
        from app.usage_sync.sync_store import SyncStore

        return SyncStore(self.settings)

    def _research_only_report(
        self,
        command: str,
        agent_plan: dict[str, Any],
        sources: list[dict[str, Any]],
        search_brief: str = "",
        *,
        memory_packet: Any | None = None,
        search_result: SearchResultPayload | None = None,
    ) -> str:
        provider = (agent_plan.get("selected_search_provider") or {}).get("id") if isinstance(agent_plan.get("selected_search_provider"), dict) else None
        source_lines = "\n".join(f"- {source.get('title')}: {source.get('url')}" for source in sources) or "- No live sources collected."
        limitations = []
        if agent_plan.get("search_unavailable"):
            limitations.append("- Web search was needed but unavailable or disabled; do not treat this as fresh research.")
        if sources:
            limitations.append("- Sources are mock-mode placeholders unless the run mode was live.")
        if self._memory_has_previous_sources(memory_packet) and not sources:
            limitations.append("- Previous memory sources were used; this is not a fresh live search.")
        limitation_text = "\n".join(limitations) or "- No additional limitations recorded."
        memory_text = self._research_memory_sections(memory_packet, search_result)
        return f"""# Research Brief

## Command
{command}

## Search Selection
- Search needed: {agent_plan.get("search_needed", False)}
- Search unavailable: {agent_plan.get("search_unavailable", False)}
- Selected provider: {provider or "none"}

## Findings
- This run prepared a research-only handoff and did not run Website Agent.
- Use the source list and limitations below before making product, pricing, competitor, or market claims.
- Current/fresh claims require live provider search approval and configured provider keys.
- Search brief: {search_brief or "No live search summary."}

{memory_text}

## Sources
{source_lines}

## Limitations
{limitation_text}
"""

    def _memory_packet_for_agent(
        self,
        *,
        agent_id: str,
        project_id: str | None,
        run_id: str,
        run_type: str,
        task: str,
        current_command: str,
        mode: str,
    ) -> Any | None:
        memory_allowed = (
            getattr(self, "_use_memory_for_current_run", True)
            and self.settings.enable_vector_memory
            and ((mode == "mock" and self.settings.memory_use_in_mock) or (mode == "live" and self.settings.memory_use_in_live))
        )
        if not memory_allowed:
            return None
        try:
            return build_context_packet(
                agent_id=agent_id,
                project_id=project_id,
                run_id=run_id,
                run_type=run_type,
                task=task,
                current_command=current_command,
                settings=self.settings,
            )
        except Exception:
            return None

    def _research_memory_sections(self, memory_packet: Any | None, search_result: SearchResultPayload | None) -> str:
        if not memory_packet or not getattr(memory_packet, "retrieved_memory_items", []):
            return """## Memory Used
- No relevant memory was retrieved for this research brief.

## Competitor Themes From Memory
- No memory themes were available.

## Source Notes
- No previous source memory was available."""
        source_memory = getattr(memory_packet, "relevant_source_memory", []) or []
        source_lines = []
        for item in source_memory[:4]:
            run_id = item.get("source_run_id") or "unknown run"
            provider = item.get("provider_id") or "unknown provider"
            source_count = item.get("source_count") or 0
            fresh = "yes" if search_result and search_result.research_used else "no"
            source_lines.append(f"- Previous source memory from run {run_id}: provider {provider}, sources {source_count}, fresh search used in this run: {fresh}.")
        if not source_lines:
            source_lines.append("- Retrieved memory did not include prior source metadata.")
        themes = self._memory_theme_lines(memory_packet)
        theme_lines = "\n".join(f"- {theme}" for theme in themes) if themes else "- No competitor themes could be safely extracted from memory."
        notes = []
        if self._memory_has_previous_sources(memory_packet):
            notes.append("- Previous memory sources were used. Do not treat them as new live search.")
        if search_result and search_result.research_used:
            notes.append("- This run also executed live search and stored fresh sources.")
        elif not (search_result and search_result.research_used):
            notes.append("- No new live search was run in this workflow.")
        source_note_text = "\n".join(notes)
        return f"""## Memory Used
{chr(10).join(source_lines)}

## Competitor Themes From Memory
{theme_lines}

## Source Notes
{source_note_text}"""

    def _memory_theme_lines(self, memory_packet: Any | None) -> list[str]:
        if not memory_packet:
            return []
        text = " ".join(
            f"{result.item.title} {result.item.summary} {result.item.content}"
            for result in getattr(memory_packet, "retrieved_memory_items", [])
        ).lower()
        themes = []
        if any(term.lower() in text for term in ("chobani", "danone", "oikos")):
            themes.append("Chobani and Danone/Oikos appear in memory as high-protein, mainstream Greek yogurt competitors.")
        if "fage" in text:
            themes.append("FAGE appears in memory as an authentic or premium Greek yogurt benchmark.")
        broad_names = ["danone", "chobani", "fage", "muller", "müller", "nestle", "nestlé", "yoplait", "lactalis"]
        found = []
        for name in broad_names:
            if name in text:
                display = {"muller": "Muller", "müller": "Muller", "nestle": "Nestle", "nestlé": "Nestle"}.get(name, name.title())
                if display not in found:
                    found.append(display)
        if found:
            themes.append(f"Memory names these competitor brands: {', '.join(found)}.")
        if any(term in text for term in ("protein", "high-protein", "high protein")):
            themes.append("Protein-forward positioning is a repeated memory theme.")
        if any(term in text for term in ("clean-label", "clean label", "ingredient", "ingredients")):
            themes.append("Clean-label ingredients and verified product claims should stay central but human-approved.")
        return themes[:5]

    def _memory_has_previous_sources(self, memory_packet: Any | None) -> bool:
        if not memory_packet:
            return False
        for item in getattr(memory_packet, "relevant_source_memory", []) or []:
            source_count = item.get("source_count") or 0
            if source_count and not item.get("search_unavailable"):
                return True
        return False

    def _memory_qa_wording(self, memory_packet: Any | None, output_text: str) -> str:
        retrieved = bool(memory_packet and getattr(memory_packet, "retrieved_memory_items", []))
        has_sources = self._memory_has_previous_sources(memory_packet)
        if not retrieved:
            return "- No relevant memory was retrieved for this run."
        lines = ["- Memory was retrieved for this run."]
        if has_sources:
            lines.append("- Previous memory sources were used.")
        if "Memory Used" not in output_text and has_sources:
            lines.append("- Warning: memory was retrieved but not reflected in an explicit Memory Used section.")
        else:
            lines.append("- Memory was reflected in the agent output.")
        lines.append("- Do not treat memory as fresh search.")
        return "\n".join(lines)

    def _website_memory_used_text(self, memory_packet: Any | None, search_result: SearchResultPayload | None) -> str:
        if not memory_packet or not getattr(memory_packet, "retrieved_memory_items", []):
            return "## Memory Used\n- No relevant memory was retrieved for this website update."
        lines = ["## Memory Used"]
        if self._memory_has_previous_sources(memory_packet):
            for item in (getattr(memory_packet, "relevant_source_memory", []) or [])[:3]:
                run_id = item.get("source_run_id") or "unknown run"
                provider = item.get("provider_id") or "unknown provider"
                source_count = item.get("source_count") or 0
                lines.append(f"- Previous source memory from run {run_id}: provider {provider}, sources {source_count}.")
            if search_result and search_result.research_used:
                lines.append("- Live search was executed in this run and sources were stored.")
            else:
                lines.append("- New live search was not used. Previous memory sources were used.")
        else:
            lines.append("- Retrieved memory did not include prior source metadata.")
        themes = self._memory_theme_lines(memory_packet)
        if themes:
            lines.append("\n## Competitor Themes From Memory")
            lines.extend(f"- {theme}" for theme in themes)
        return "\n".join(lines)

    def _is_homepage_copy_task(self, command: str) -> bool:
        text = command.lower()
        copy_terms = ("homepage copy", "landing page copy", "improve homepage", "update hero", "update website copy", "only update homepage", "homepage content")
        backend_terms = ("status page", "order tracking", "backend", "app.py", "requirements", "dependencies", "sample orders")
        return any(term in text for term in copy_terms) and not any(term in text for term in backend_terms)

    def _website_scope_plan(self, command: str, homepage_copy_task: bool, changed_files: list[str], system_metadata_files: list[str]) -> str:
        if homepage_copy_task:
            allowed = ["website/templates/index.html", "website/data/faqs.json", "website/README.md"]
            blocked = ["website/app.py", "website/requirements.txt", "website/templates/status.html", "website/data/order_statuses.json", "website/data/sample_orders.json"]
            task_type = "homepage_copy"
            reason = "copy-only update does not require backend/app/dependency/order-data changes"
        else:
            allowed = ["website/**"]
            blocked = ["deployments", "package installs", ".env and secret files"]
            task_type = "website_update"
            reason = "website workflow may update prototype files but must remain inside the project workspace"
        return f"""## Website Scope Plan
* User requested: {command}
* task_type: {task_type}
* Allowed target files:
{chr(10).join(f'  * {path}' for path in allowed)}
* Files intentionally not touched:
{chr(10).join(f'  * {path}' for path in blocked)}
* Changed files:
{chr(10).join(f'  * {path}' for path in changed_files) if changed_files else '  * None yet'}
* System metadata files:
{chr(10).join(f'  * {path}' for path in system_metadata_files)}
* Reason: {reason}
"""

    def _save_real_coding_artifacts(self, run_id: str, result: RealCodingAgentResult) -> list[Any]:
        payload = result.model_dump()
        artifacts = [
            self.artifacts.save_text(
                run_id=run_id,
                name="coding_context.json",
                artifact_type="json",
                content=json.dumps(
                    {
                        "files_inspected": result.files_inspected,
                        "files_selected": result.files_selected,
                        "memory_used": result.memory_used,
                        "search_context_used": result.search_context_used,
                    },
                    indent=2,
                ),
                agent_name="Real Coding Agent",
                summary="Compact coding context metadata; protected files are excluded.",
            ),
            self.artifacts.save_text(
                run_id=run_id,
                name="file_scope_plan.json",
                artifact_type="json",
                content=json.dumps(
                    {
                        "task_type": result.task_type,
                        "allowed_user_file_scope": result.allowed_user_file_scope.model_dump(),
                        "files_selected": result.files_selected,
                        "files_changed": result.files_changed,
                        "rejected_files": result.rejected_files,
                        "no_change_reason": result.no_change_reason,
                        "hardcoded_fallback_used": result.hardcoded_fallback_used,
                    },
                    indent=2,
                ),
                agent_name="Real Coding Agent",
                summary="Real Coding Agent file scope plan.",
            ),
            self.artifacts.save_text(
                run_id=run_id,
                name="coding_plan.md",
                artifact_type="markdown",
                content=self._real_coding_plan_markdown(result),
                agent_name="Real Coding Agent",
                summary="Coding plan and model selection notes.",
            ),
            self.artifacts.save_text(
                run_id=run_id,
                name="proposed_patch.json",
                artifact_type="json",
                content=json.dumps(payload.get("proposed_patch") or {}, indent=2),
                agent_name="Real Coding Agent",
                summary="Structured patch proposed by the coding model or mock simulator.",
            ),
            self.artifacts.save_text(
                run_id=run_id,
                name="applied_patch_summary.json",
                artifact_type="json",
                content=json.dumps({"patch_applied": result.patch_applied, "dry_run": result.dry_run, "applied_files": payload.get("applied_files", [])}, indent=2),
                agent_name="Real Coding Agent",
                summary="Applied patch summary with before/after diffs.",
            ),
            self.artifacts.save_text(
                run_id=run_id,
                name="validation_result.json",
                artifact_type="json",
                content=json.dumps({"validation": payload.get("validation"), "commands": result.validation_commands}, indent=2),
                agent_name="Real Coding Agent",
                summary="Patch validation and command validation result.",
            ),
        ]
        if result.provider_response_diagnostic:
            artifacts.append(
                self.artifacts.save_text(
                    run_id=run_id,
                    name="coding_provider_response_diagnostic.json",
                    artifact_type="json",
                    content=json.dumps(result.provider_response_diagnostic, indent=2),
                    agent_name="Real Coding Agent",
                    summary="Safe provider response diagnostics for invalid live coding output.",
                )
            )
        for artifact_name, payload_key in [
            ("repair_policy.json", "repair_policy"),
            ("repair_attempt_1_context.json", "repair_attempt_1_context"),
            ("repair_attempt_1_result.json", "repair_attempt_1_result"),
            ("repair_validation_result.json", "repair_validation_result"),
            ("rollback_result.json", "rollback_result"),
        ]:
            payload = result.repair_loop.artifacts.get(payload_key)
            if payload and (result.repair_loop.repair_enabled or result.repair_loop.attempts_made or result.repair_loop.rollback_attempted):
                artifacts.append(
                    self.artifacts.save_text(
                        run_id=run_id,
                        name=artifact_name,
                        artifact_type="json",
                        content=json.dumps(payload, indent=2),
                        agent_name="Real Coding Agent",
                        summary="Bounded coding repair loop metadata.",
                    )
                )
        artifacts.append(
            self.artifacts.save_text(
                run_id=run_id,
                name="real_coding_agent_report.md",
                artifact_type="markdown",
                content=self._real_coding_report(result),
                agent_name="Real Coding Agent",
                summary="Human-readable Real Coding Agent report.",
            )
        )
        return artifacts

    def _real_coding_plan_markdown(self, result: RealCodingAgentResult) -> str:
        return f"""# Real Coding Agent Plan

## Model
- Selected model: {result.selected_model}
- Provider: {result.actual_provider}
- Fallback model: {result.fallback_model or "none"}
- Fallback used: {result.fallback_model_used}
- Live call made: {result.live_call_made}
- Mock simulated: {result.mock_simulated}
- Requested max output tokens: {result.requested_max_output_tokens or "n/a"}
- GPT-5.5 not used: true

## Scope
- Task type: {result.task_type}
- Files inspected: {len(result.files_inspected)}
- Files selected: {", ".join(result.files_selected) or "none"}
- Dry run: {result.dry_run}
- Template fallback used: {result.hardcoded_fallback_used}
- Parser route: {result.parser_route or "n/a"}
- Parse error: {result.parse_error or "none"}
"""

    def _real_coding_report(self, result: RealCodingAgentResult) -> str:
        validation = "accepted" if result.validation.accepted else "rejected"
        return f"""# Real Coding Agent v1 Report

## Status
- Real coding enabled: {result.enabled}
- Real coding used: {result.used}
- Actual provider: {result.actual_provider}
- Selected model: {result.selected_model}
- Fallback model: {result.fallback_model or "none"}
- Fallback model used: {result.fallback_model_used}
- Live call made: {result.live_call_made}
- Mock simulated: {result.mock_simulated}
- Dry run: {result.dry_run}
- Patch applied: {result.patch_applied}
- No change reason: {result.no_change_reason or "n/a"}
- Hardcoded fallback used: {result.hardcoded_fallback_used}
- Requested max output tokens: {result.requested_max_output_tokens or "n/a"}
- Parser route: {result.parser_route or "n/a"}
- Parse error: {result.parse_error or "none"}

## Repair Loop
- Repair enabled: {result.repair_loop.repair_enabled}
- Repair attempts: {result.repair_loop.attempts_made} / {result.repair_loop.max_attempts}
- Initial validation: {"failed" if result.repair_loop.initial_validation_failed else "not failed"}
- Repair validation: {"passed" if result.repair_loop.repair_validation_passed is True else "failed" if result.repair_loop.repair_validation_passed is False else "n/a"}
- Rollback: {"succeeded" if result.repair_loop.rollback_succeeded is True else "failed" if result.repair_loop.rollback_succeeded is False else "not attempted"}
- Final result: {result.repair_loop.final_result}

## Files
- Inspected: {", ".join(result.files_inspected[:20]) or "none"}
- Selected: {", ".join(result.files_selected) or "none"}
- Changed: {", ".join(result.files_changed) or "none"}
- Rejected: {", ".join(result.rejected_files) or "none"}

## Validation
- Patch validation: {validation}
- Violations: {"; ".join(result.validation.violations) or "none"}
- Warnings: {"; ".join(result.validation.warnings) or "none"}
- Patch-specific validation commands: {len(result.validation_commands)}

## Memory
- Primary memory source: {result.memory_used[0].get("title") if result.memory_used else "none"}
- Why used: {", ".join(result.memory_used[0].get("why_selected", [])) if result.memory_used else "n/a"}
- Excluded low-quality memory: {"; ".join(result.memory_exclusions) or "none"}

## Notes
{chr(10).join(f"- {note}" for note in result.notes)}
"""

    def _template_fallback_result(self, command: str, model: str, changed_files: list[str], homepage_copy_task: bool) -> RealCodingAgentResult:
        return RealCodingAgentResult(
            enabled=self.settings.enable_real_coding_agent,
            used=False,
            actual_provider="mock",
            selected_model=model,
            fallback_model=self.settings.real_coding_agent_fallback_model,
            live_call_made=False,
            mock_simulated=True,
            dry_run=False,
            hardcoded_fallback_used=True,
            patch_applied=True,
            task_type="website_copy_update" if homepage_copy_task else "website_ui_update",
            allowed_user_file_scope=prompt_file_scope(command, "website_copy_update" if homepage_copy_task else "website_ui_update"),
            files_inspected=changed_files,
            files_selected=changed_files,
            files_changed=changed_files,
            validation=PatchValidationResult(
                accepted=True,
                warnings=["Deterministic Greek yogurt builder is a mock/demo fallback. Real Coding Agent should be used for general project edits."],
            ),
            notes=[
                "Template fallback used. No real coding model call was made.",
                "Deterministic Greek yogurt builder is a mock/demo fallback and should not be expanded for general coding tasks.",
                f"Command: {command[:300]}",
            ],
        )

    def _real_coding_final_action(self, result: RealCodingAgentResult | None) -> str:
        if result is None:
            return "Updated website files."
        if result.hardcoded_fallback_used:
            return "Used deterministic template fallback; no real coding model call was made."
        if result.repair_loop.final_result == "repaired_successfully":
            return "Initial validation failed, then one bounded Real Coding Agent repair patch passed validation and was retained."
        if result.repair_loop.rollback_attempted:
            return "Initial and repair validation failed; original pre-run file contents were restored."
        if result.dry_run:
            return "Real Coding Agent prepared and validated a dry-run patch without applying file changes."
        if result.patch_applied:
            return "Real Coding Agent inspected files, generated a structured patch, validated it, and applied approved file changes."
        if result.parse_error:
            return f"No user-facing file changes were applied because the live coding provider output was rejected before patch application. Reason: {result.parse_error}."
        if result.live_call_made and not result.validation.accepted:
            reason = "; ".join(result.validation.violations) or "patch validation rejected the proposed change"
            return f"No user-facing file changes were applied because the live coding provider output was rejected before patch application. Reason: {reason}."
        return "Real Coding Agent inspected files and validated the proposed patch without applying changes."

    def _real_coding_qa_report_line(self, result: RealCodingAgentResult | None) -> str:
        if result and result.patch_applied:
            if result.repair_loop.final_result == "repaired_successfully":
                return "Ran QA after repaired file changes. Initial validation failed, repair validation passed."
            return "Ran QA after approved file changes."
        if result and result.repair_loop.rollback_attempted:
            return "Ran QA after failed repair validation. Original files were restored before stopping."
        if result and result.validation.accepted and result.dry_run:
            return "Ran QA after dry-run patch validation. No file changes were applied because dry-run mode was enabled."
        if result and not result.validation.accepted:
            return "Ran QA after patch rejection. No file changes were applied because patch validation failed."
        return "Ran QA after patch validation."

    def _prototype_final_report(
        self,
        command: str,
        project_id: str | None,
        file_entries: list[Any],
        command_results: list[CommandResult],
        artifact_records: list[Any],
        task_packets: list[TaskPacket],
    ) -> str:
        files = "\n".join(f"- {entry.path} ({entry.operation}, {entry.size_bytes} bytes)" for entry in file_entries)
        commands = "\n".join(
            f"- `{' '.join(result.command)}` in `{result.cwd}` -> exit {result.exit_code}"
            + (f" blocked: {result.blocked_reason}" if result.blocked_reason else "")
            for result in command_results
        )
        packets = "\n".join(f"- {packet.agent_name}: {packet.objective}" for packet in task_packets)
        artifacts = "\n".join(f"- {artifact.name} [{artifact.type}]" for artifact in artifact_records)
        return f"""# Persistent Project Workspace v1 Report

## Command
{command}

## Project
{project_id or "unassigned"}

## Task Packets
{packets}

## Files Created Or Edited
{files}

## Safe Commands Run
{commands}

## Artifacts Registered
{artifacts}

## Safety Notes
- Project work stayed inside the persistent project workspace.
- Run logs were saved separately from project files.
- No live API calls, emails, social posts, production deploys, package installs, or dangerous shell commands were performed.
- The generated Python file was validated with `python -m py_compile` when safe commands were allowed.
"""

    def _update_prototype_memory(
        self,
        *,
        run_id: str,
        project_id: str | None,
        run_type: str,
        command: str,
        file_entries: list[Any],
        command_results: list[CommandResult],
        artifact_records: list[Any],
        task_packets: list[TaskPacket],
        cost: float,
    ) -> list[str]:
        files = [entry.path for entry in file_entries]
        commands = [" ".join(result.command) for result in command_results]
        update_current_state(
            f"Last Persistent Project Workspace v1 run: {command}. Project: {project_id or 'unassigned'}. "
            f"Run ID: {run_id}. Files: {', '.join(files)}. Commands: {', '.join(commands)}. "
            f"Estimated cost: ${cost:.6f}."
        )
        vector_memory = LocalVectorMemory(str(self.settings.vector_path))
        vector_memory.add_chunk(
            f"Project workspace run {run_id}",
            (
                f"Project id: {project_id}. Run type: {run_type}. Files changed: {', '.join(files)}. "
                f"Commands run: {', '.join(commands)}. Artifacts: {', '.join(artifact.name for artifact in artifact_records)}."
            ),
        )
        embedding_memory = EmbeddingMemory(self.settings)
        memory_ids = []
        memory_ids.append(
            embedding_memory.add_memory(
                text=(
                    f"Persistent project run {run_id} changed files {', '.join(files)}. "
                    f"Command results: {', '.join(f'{result.command}:{result.exit_code}' for result in command_results)}. "
                    f"Task packets: {', '.join(packet.task_id for packet in task_packets)}."
                ),
                metadata={
                    "project_id": project_id,
                    "run_id": run_id,
                    "agent_name": "TheHiveMind",
                    "artifact_id": None,
                    "memory_type": "project_update",
                    "tags": ["persistent_project_workspace", run_type],
                },
            )
        )
        for entry in file_entries:
            memory_ids.append(
                embedding_memory.add_memory(
                    text=f"File change for project {project_id}: {entry.path} was {entry.operation}.",
                    metadata={
                        "project_id": project_id,
                        "run_id": run_id,
                        "agent_name": getattr(entry, "agent_name", "File Builder Agent"),
                        "file_path": entry.path,
                        "artifact_id": None,
                        "memory_type": "file_change",
                        "tags": ["file_change", run_type],
                    },
                )
            )
        for artifact in artifact_records:
            memory_ids.append(
                embedding_memory.add_memory(
                    text=f"Artifact {artifact.name}: {artifact.summary}. Path: {artifact.path}",
                    metadata={
                        "project_id": project_id,
                        "run_id": run_id,
                        "agent_name": artifact.agent_name,
                        "artifact_id": artifact.id,
                        "memory_type": "agent_decision" if artifact.agent_name != "File Builder Agent" else "artifact_summary",
                        "tags": ["artifact", artifact.type],
                    },
                )
            )
        return memory_ids

    def _agent_info(self, agent: Any) -> AgentInfo:
        return AgentInfo(
            name=agent.name,
            role=agent.role,
            assigned_model=agent.assigned_model,
            status="completed",
            latest_action="Completed Run Engine v1 step",
            completed_work=[f"Produced controlled output for {agent.role}."],
        )

    def _update_memory(self, record: RunRecord, model_selection: dict[str, Any]) -> None:
        update_current_state(
            f"Last Run Engine v1 run: {record.command}. Project: {record.project_id or 'unassigned'}. "
            f"Run ID: {record.run_id}. Artifacts: {', '.join(artifact.name for artifact in record.artifacts)}. "
            f"Estimated cost: ${record.metrics.total_estimated_cost_usd:.6f}."
        )
        vector_memory = LocalVectorMemory(str(self.settings.vector_path))
        vector_memory.add_chunk(
            f"Run summary {record.run_id}",
            (
                f"Project id: {record.project_id}. Run type: {record.run_type}. "
                f"Summary: {record.final_output.summary}. "
                f"Artifacts: {', '.join(artifact.name for artifact in record.artifacts)}. "
                f"Model choices: {json.dumps(model_selection['models'], ensure_ascii=True)}. "
                f"Cost: {record.metrics.total_estimated_cost_usd}."
            ),
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
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (run_id, command, status, created_at, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (record.run_id, record.command, record.status, record.started_at.isoformat(), record.model_dump_json()),
            )
