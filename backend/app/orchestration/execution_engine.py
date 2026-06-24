import hashlib
import html
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
from app.core.cost_estimator import assert_run_budget, estimate_cost, estimate_cost_usd, estimate_messages_tokens, estimate_tokens
from app.core.model_registry import get_model_metadata
from app.core.models import AgentInfo, BusinessIntake, FinalOutput, RunEvent, RunMetrics, RunRecord
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
    business_intake: BusinessIntake | None = None,
    business_phase: str = "phase_1",
    source_run_id: str | None = None,
    confirm_local_prototype: bool = False,
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
        business_intake=business_intake,
        business_phase=business_phase,
        source_run_id=source_run_id,
        confirm_local_prototype=confirm_local_prototype,
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
        business_intake: BusinessIntake | None = None,
        business_phase: str = "phase_1",
        source_run_id: str | None = None,
        confirm_local_prototype: bool = False,
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
        if run_type == "business_builder":
            if business_phase == "phase_2a_local_prototype":
                return await self._execute_business_builder_phase2a(
                    command=command,
                    mode=mode,
                    project_id=project_id,
                    allow_file_writes=allow_file_writes,
                    allow_safe_commands=allow_safe_commands,
                    allow_web_search=allow_web_search,
                    allow_ceo_live=allow_ceo_live,
                    use_memory=use_memory,
                    use_real_coding_agent=use_real_coding_agent,
                    allow_live_coding_model_call=allow_live_coding_model_call,
                    real_coding_dry_run=real_coding_dry_run,
                    real_coding_model=real_coding_model,
                    real_coding_max_files=real_coding_max_files,
                    real_coding_max_repair_attempts=real_coding_max_repair_attempts,
                    source_run_id=source_run_id,
                    confirm_local_prototype=confirm_local_prototype,
                    run_id=run_id,
                    started_at=started_at,
                    memory=memory,
                )
            return await self._execute_business_builder(
                command=command,
                mode=mode,
                project_id=project_id,
                allow_ceo_live=allow_ceo_live,
                allow_web_search=allow_web_search,
                max_cost=max_cost,
                run_id=run_id,
                started_at=started_at,
                memory=memory,
                business_intake=business_intake,
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

    async def _execute_business_builder(
        self,
        *,
        command: str,
        mode: str,
        project_id: str | None,
        allow_ceo_live: bool,
        allow_web_search: bool,
        max_cost: float,
        run_id: str,
        started_at: datetime,
        memory,
        business_intake: BusinessIntake | None,
    ) -> RunRecord:
        if business_intake is None or not business_intake.idea.strip():
            raise HTTPException(status_code=422, detail="business_builder requires business_intake.idea.")
        if mode == "live" and not allow_ceo_live:
            raise HTTPException(status_code=403, detail="Business Builder live planning requires allow_ceo_live=true and the existing CEO approval gate.")

        active_project_id = project_id or "business-builder-phase1"
        project_manager = ProjectWorkspaceManager(self.settings)
        project_workspace = project_manager.ensure_project_workspace(active_project_id)
        project_root = project_manager.get_project_root(active_project_id)
        project_manager.create_run_log_folder(run_id)
        agent_plan = self._plan_run(
            command=command,
            run_type="business_builder",
            project_id=active_project_id,
            mode=mode,
            allow_file_writes=False,
            allow_safe_commands=False,
            allow_web_search=allow_web_search,
            max_cost=max_cost,
        )
        selected_models = self._selection_by_agent(agent_plan)
        planner_selection = selected_models.get("business_planner_agent") or {}
        planner_model = str(planner_selection.get("selected_model_id") or ("gpt-5.5" if mode == "live" else "mock_business_planner"))
        qa_model = _selected_model_id(selected_models, "qa_agent", self.settings.cheap_worker_model)
        artifact_records = []
        agent_plan_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="agent_plan.json",
            artifact_type="json",
            content=agent_plan.model_dump_json(indent=2),
            agent_name="Business Planner",
            summary="Selected Business Builder Phase 1 workflow and constraints.",
        )
        model_selection_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="model_selection.json",
            artifact_type="json",
            content=json.dumps(selected_models, indent=2),
            agent_name="Business Planner",
            summary="Per-agent model choices for Business Builder Phase 1.",
        )
        artifact_records.extend([agent_plan_artifact, model_selection_artifact])
        search_result: SearchResultPayload | None = None
        research_event: RunEvent | None = None
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
            research_summary = f"Controlled research context collected for Phase 1 planning. Sources: {len(search_result.sources)}."
            research_event = self._manual_step(
                run_id=run_id,
                mode=mode,
                agent_name="Research Agent",
                agent_role="Optional Phase 1 research context",
                model=_selected_model_id(selected_models, "research_agent", self.settings.cheap_search_worker_model),
                request_type="business_builder_research",
                input_text=command,
                output_text=research_summary,
                action_summary="Collected optional research context for Business Builder Phase 1",
                artifact_id=agent_plan_artifact.id,
            )
        intake_payload = self._business_intake_payload(business_intake)
        research_status = {
            "enabled": bool(allow_web_search),
            "used": bool(search_result and search_result.sources),
            "source_count": len(search_result.sources) if search_result else 0,
        }
        deterministic_bundle = self._business_builder_bundle(
            command=command,
            intake=intake_payload,
            allow_web_search=allow_web_search,
            memory_retrieved_count=len(memory.retrieved_snippets),
            research_status=research_status,
        )
        if mode == "live":
            planning_bundle, planner_event = await self._run_live_business_builder_planner(
                command=command,
                project_id=active_project_id,
                run_id=run_id,
                max_cost=max_cost,
                intake=intake_payload,
                deterministic_bundle=deterministic_bundle,
                research_status=research_status,
                memory_retrieved_count=len(memory.retrieved_snippets),
                artifact_id=agent_plan_artifact.id,
            )
        else:
            planning_bundle = deterministic_bundle
            planner_event = self._business_builder_event(
                run_id=run_id,
                mode=mode,
                agent_name="Business Planner",
                agent_role="Business Builder Phase 1 planning",
                model="mock_business_planner",
                provider="mock",
                input_text=json.dumps({"command": command, "business_intake": intake_payload, "phase": 1}, indent=2),
                output_text=planning_bundle["final_planning_report.md"],
                action_summary="Created Business Builder Phase 1 planning package with deterministic mock planner",
                artifact_id=agent_plan_artifact.id,
                estimated_model="gpt-5.5",
            )

        planning_artifact_names = [
            "strategic_decisions.json",
            "business_brief.json",
            "business_brief.md",
            "business_strategy.md",
            "target_customer.md",
            "offer_and_pricing.md",
            "brand_direction.md",
            "website_app_requirements.md",
            "mvp_scope.md",
            "build_handoff.json",
            "business_builder_state.json",
        ]
        for name in planning_artifact_names:
            content = planning_bundle[name]
            artifact_records.append(
                self.artifacts.save_text(
                    run_id=run_id,
                    name=name,
                    artifact_type="json" if name.endswith(".json") else "markdown",
                    content=content if isinstance(content, str) else json.dumps(content, indent=2),
                    agent_name="Business Planner",
                    summary=f"Business Builder Phase 1 artifact: {name}.",
                )
            )
        qa_text = self._business_builder_qa(planning_bundle)
        qa_event = self._business_builder_event(
            run_id=run_id,
            mode=mode,
            agent_name="Planning QA",
            agent_role="Phase 1 planning review",
            model=qa_model,
            provider=get_model_metadata(qa_model).provider,
            input_text=f"Review Business Builder Phase 1 artifacts for safety and completeness.\n{json.dumps(planning_bundle['business_brief.json'], indent=2)}",
            output_text=qa_text,
            action_summary="Reviewed Business Builder Phase 1 package",
            artifact_id="",
        )
        qa_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="planning_qa.md",
            artifact_type="markdown",
            content=qa_text,
            agent_name="Planning QA",
            summary="QA review for Business Builder Phase 1.",
        )
        qa_event.artifact_id = qa_artifact.id
        final_artifact = self.artifacts.save_text(
            run_id=run_id,
            name="final_planning_report.md",
            artifact_type="markdown",
            content=planning_bundle["final_planning_report.md"],
            agent_name="Business Planner",
            summary="Executive planning report for Business Builder Phase 1.",
        )
        artifact_records.extend([qa_artifact, final_artifact])
        events = [event for event in [research_event, planner_event, qa_event] if event is not None]
        completed_at = datetime.now(UTC)
        metrics = RunMetrics(
            total_estimated_tokens=sum(event.estimated_tokens or event.estimated_input_tokens + event.estimated_output_tokens for event in events),
            total_estimated_cost_usd=round(sum(event.estimated_cost_usd for event in events), 6),
            agents_used=len({event.agent_name for event in events}),
            tasks_completed=len(events),
            run_duration_seconds=round((completed_at - started_at).total_seconds(), 3),
            memory_chunks_retrieved=len(memory.retrieved_snippets),
        )
        assert_run_budget(metrics.total_estimated_cost_usd)
        if metrics.total_estimated_cost_usd > max_cost:
            raise HTTPException(status_code=400, detail=f"Estimated run cost ${metrics.total_estimated_cost_usd:.6f} exceeds request max_cost_usd=${max_cost:.2f}.")

        state_entry = project_manager.write_project_file(
            active_project_id,
            "business_builder_state.json",
            json.dumps(planning_bundle["business_builder_state.json"], indent=2),
            "Business Planner",
            run_id,
            "Latest Business Builder Phase 1 planning state.",
        )
        project_state_content = update_project_state(
            project_root / "project_state.md",
            project_id=active_project_id,
            run_id=run_id,
            command=command,
            files_created=[],
            files_edited=[state_entry.path],
            command_success=True,
            next_steps=["Review Phase 1 planning package.", "Approve or revise assumptions before requesting Phase 2."],
        )
        project_manager.write_project_file(active_project_id, "project_state.md", project_state_content, "Project Workspace Manager", run_id, "Latest project state after business_builder Phase 1.")
        project_manifest = project_manager.append_project_run(active_project_id, run_id, f"Business Builder Phase 1 planning completed for: {business_intake.idea.strip()}")
        project_manifest_artifact = self.artifacts.register_file(
            run_id=run_id,
            name="project_manifest.json",
            artifact_type="project_manifest",
            path=str(project_root / "manifest.json"),
            agent_name="Project Workspace Manager",
            summary="Persistent project manifest after business_builder.",
        )
        project_state_artifact = self.artifacts.register_file(
            run_id=run_id,
            name="project_state.md",
            artifact_type="project_state",
            path=str(project_root / "project_state.md"),
            agent_name="Project Workspace Manager",
            summary="Updated project state.",
        )
        artifact_records.extend([project_manifest_artifact, project_state_artifact])
        project_manager.write_run_logs(
            run_id=run_id,
            run_summary={
                "run_id": run_id,
                "project_id": active_project_id,
                "run_type": "business_builder",
                "status": "completed",
                "selected_workflow": agent_plan.selected_workflow,
                "agent_plan": agent_plan.model_dump(),
                "model_selection": selected_models,
                "files_created": [],
                "files_edited": [state_entry.path],
                "commands": [],
                "estimated_cost_usd": metrics.total_estimated_cost_usd,
            },
            timeline=[event.model_dump() for event in events],
            commands=[],
            project_manifest=project_manifest,
        )
        record = RunRecord(
            run_id=run_id,
            command=command,
            mode=mode,
            project_id=active_project_id,
            run_type="business_builder",
            status="completed",
            started_at=started_at,
            completed_at=completed_at,
            events=events,
            agents=[
                AgentInfo(name="Business Planner", role="Business Builder Phase 1 planning", assigned_model=planner_model, status="completed", latest_action="Created planning package", completed_work=planning_artifact_names),
                AgentInfo(name="Planning QA", role="Phase 1 planning review", assigned_model=qa_model, status="completed", latest_action="Reviewed planning package", completed_work=["Created planning_qa.md"]),
            ],
            task_graph=build_default_task_graph(),
            metrics=metrics,
            memory=memory,
            final_output=FinalOutput(
                summary=f"Business Builder Phase 1 planning package completed for project {active_project_id}.",
                what_was_done=[
                    "Selected workflow: business_builder.",
                    "Created Phase 1 planning artifacts only.",
                    "Build status: Not built.",
                    "Real Coding Agent was not used.",
                    "No website, app, deployment, external integration, payment flow, social post, ad campaign, or external action was created.",
                ],
                recommended_next_actions=["Review facts, assumptions, unresolved decisions, and approvals.", "Request Phase 2 only after the handoff is reviewed and approved."],
                generated_artifacts=[artifact.name for artifact in artifact_records],
            ),
            artifacts=artifact_records,
            workspace=WorkspaceSummary(root=project_manager.public_root(active_project_id), files_created=[], files_edited=[state_entry.path], commands_run=[], command_success=True),
            project_workspace=ProjectWorkspaceSummary(project_id=active_project_id, root=project_workspace.root, files_created=[], files_edited=[state_entry.path], commands_run=[], command_success=True),
            models_used=sorted({event.model_used for event in events}),
            project_files_created=[],
            project_files_updated=[state_entry.path],
            commands_run=[],
            usage_summary={
                "estimated_cost_usd": metrics.total_estimated_cost_usd,
                "estimated_tokens": metrics.total_estimated_tokens,
                "agents_used": metrics.agents_used,
                "models_used": sorted({event.model_used for event in events}),
                "selected_workflow": agent_plan.selected_workflow,
                "search_needed": agent_plan.search_needed,
                "search_unavailable": agent_plan.search_unavailable,
                "business_builder": {
                    "phase": 1,
                    "planning_version": planning_bundle["business_brief.json"].get("planning_version", "1.1"),
                    "status": "planning_complete",
                    "build_status": "Not built",
                    "build_started": False,
                    "build_allowed": False,
                    "primary_launch_segment": planning_bundle["business_brief.json"].get("primary_launch_segment"),
                    "secondary_segments": planning_bundle["business_brief.json"].get("secondary_segments", []),
                    "local_build_readiness": planning_bundle["business_brief.json"].get("local_build_readiness", {}),
                    "public_launch_readiness": planning_bundle["business_brief.json"].get("public_launch_readiness", {}),
                    "execution_mode": "live_strategic_planner" if mode == "live" else "deterministic_mock_planner",
                    "actual_provider": planner_event.provider,
                    "actual_model": planner_event.model_used,
                    "live_strategic_planner_target": "gpt-5.5",
                    "live_call_made": mode == "live",
                    "provider_call_status": "success" if mode == "live" else "not_called_mock",
                    "search_status": planning_bundle["business_brief.json"]["research_status"],
                    "memory_status": {"retrieval_enabled": len(memory.retrieved_snippets) > 0, "retrieved_count": len(memory.retrieved_snippets)},
                    "approvals_needed": planning_bundle["business_brief.json"]["approvals_needed"],
                    "blocked_external_actions": planning_bundle["business_builder_state.json"]["external_actions_blocked"],
                    "deferred_to_phase_2": planning_bundle["business_builder_state.json"]["deferred_to_phase_2"],
                },
            },
            memory_updates=[],
            agent_plan=agent_plan.model_dump(),
            model_selection=selected_models,
        )
        return self._finalize_run(record)

    async def _execute_business_builder_phase2a(
        self,
        *,
        command: str,
        mode: str,
        project_id: str | None,
        allow_file_writes: bool,
        allow_safe_commands: bool,
        allow_web_search: bool,
        allow_ceo_live: bool,
        use_memory: bool,
        use_real_coding_agent: bool,
        allow_live_coding_model_call: bool,
        real_coding_dry_run: bool,
        real_coding_model: str | None,
        real_coding_max_files: int | None,
        real_coding_max_repair_attempts: int,
        source_run_id: str | None,
        confirm_local_prototype: bool,
        run_id: str,
        started_at: datetime,
        memory,
    ) -> RunRecord:
        active_project_id = project_id or ""
        self._validate_phase2a_entry(
            mode=mode,
            project_id=active_project_id,
            allow_file_writes=allow_file_writes,
            allow_safe_commands=allow_safe_commands,
            allow_web_search=allow_web_search,
            allow_ceo_live=allow_ceo_live,
            use_memory=use_memory,
            use_real_coding_agent=use_real_coding_agent,
            allow_live_coding_model_call=allow_live_coding_model_call,
            real_coding_dry_run=real_coding_dry_run,
            real_coding_model=real_coding_model,
            real_coding_max_files=real_coding_max_files,
            real_coding_max_repair_attempts=real_coding_max_repair_attempts,
            source_run_id=source_run_id,
            confirm_local_prototype=confirm_local_prototype,
        )
        source = self._load_phase2a_source_run(source_run_id or "", active_project_id)
        project_manager = ProjectWorkspaceManager(self.settings)
        project_workspace = project_manager.ensure_project_workspace(active_project_id)
        project_manager.create_run_log_folder(run_id)

        policy = self._phase2a_policy()
        build_spec = self._phase2a_build_spec(source["strategic_decisions"], source["build_handoff"], policy)
        prototype_files = self._render_phase2a_prototype_files(build_spec, policy, source_run_id or "", active_project_id, run_id)
        generated_entries = [
            project_manager.write_project_file(
                active_project_id,
                f"prototypes/{run_id}/{name}",
                content,
                "Local Prototype Renderer",
                run_id,
                f"Business Builder Phase 2A local prototype file {name}.",
            )
            for name, content in prototype_files.items()
        ]
        file_manifest = self._phase2a_file_manifest(project_manager, active_project_id, run_id, source_run_id or "", [entry.path for entry in generated_entries])
        technical_qa = self._phase2a_technical_qa(project_manager, active_project_id, run_id)
        if "BLOCKED:" in technical_qa:
            raise HTTPException(status_code=500, detail="Business Builder Phase 2A technical QA failed; prototype was not marked completed.")
        visual_qa = "WARN: Visual evidence not captured because the existing local browser runtime was unavailable."
        state = {
            "phase": "2a",
            "status": "local_prototype_completed",
            "source_run_id": source_run_id,
            "prototype_mode": "local_demo_only",
            "prototype_created": True,
            "public_launch_allowed": False,
            "external_actions_taken": [],
            "personal_data_collected": False,
            "provider_calls": 0,
        }
        final_report = self._phase2a_final_report(active_project_id, run_id, source_run_id or "", file_manifest, technical_qa, visual_qa)

        artifact_payloads = {
            "phase2a_source_handoff.json": source["source_handoff"],
            "phase2a_policy.json": policy,
            "phase2a_build_spec.json": build_spec,
            "prototype_file_manifest.json": file_manifest,
            "prototype_technical_qa.md": technical_qa,
            "prototype_visual_qa.md": visual_qa,
            "prototype_final_report.md": final_report,
            "phase2a_local_prototype_state.json": state,
        }
        artifact_records = []
        for name, content in artifact_payloads.items():
            artifact_records.append(
                self.artifacts.save_text(
                    run_id=run_id,
                    name=name,
                    artifact_type="json" if name.endswith(".json") else "markdown",
                    content=content if isinstance(content, str) else json.dumps(content, indent=2),
                    agent_name=self._phase2a_artifact_agent(name),
                    summary=f"Business Builder Phase 2A artifact: {name}.",
                )
            )

        events = [
            self._phase2a_event(run_id, "Source Handoff Validator", "Validated immutable Phase 1.1 handoff", "Validated completed source run, required artifacts, project match, public-launch boundary, and external-action history.", artifact_records[0].id),
            self._phase2a_event(run_id, "Phase 2A Policy Compiler", "Compiled deterministic local-demo policy", "System policy narrowed the prototype to local demo-only behavior.", artifact_records[1].id),
            self._phase2a_event(run_id, "Local Prototype Renderer", "Rendered local HTML prototype files", f"Generated {len(generated_entries)} files under prototypes/{run_id}/.", artifact_records[3].id),
            self._phase2a_event(run_id, "Technical QA", "Verified local prototype safety checks", technical_qa, artifact_records[4].id),
            self._phase2a_event(run_id, "Visual Evidence Capture", "Recorded visual evidence status", visual_qa, artifact_records[5].id),
            self._phase2a_event(run_id, "Final Prototype Report", "Prepared Phase 2A completion report", final_report, artifact_records[6].id),
        ]
        completed_at = datetime.now(UTC)
        metrics = RunMetrics(
            total_estimated_tokens=0,
            total_estimated_cost_usd=0,
            agents_used=len(events),
            tasks_completed=len(events),
            run_duration_seconds=round((completed_at - started_at).total_seconds(), 3),
            memory_chunks_retrieved=0,
        )
        project_manifest = project_manager.append_project_run(active_project_id, run_id, f"Business Builder Phase 2A local prototype completed from source run {source_run_id}.")
        project_manager.write_run_logs(
            run_id=run_id,
            run_summary={
                "run_id": run_id,
                "project_id": active_project_id,
                "run_type": "business_builder",
                "business_phase": "phase_2a_local_prototype",
                "status": "completed",
                "selected_workflow": "business_builder_phase2a_local_prototype",
                "files_created": [entry.path for entry in generated_entries],
                "files_edited": [],
                "commands": [],
                "estimated_cost_usd": 0,
            },
            timeline=[event.model_dump() for event in events],
            commands=[],
            project_manifest=project_manifest,
        )
        record = RunRecord(
            run_id=run_id,
            command=command,
            mode="mock",
            project_id=active_project_id,
            run_type="business_builder",
            status="completed",
            started_at=started_at,
            completed_at=completed_at,
            events=events,
            agents=[
                AgentInfo(name=event.agent_name, role=event.agent_role, assigned_model="none", status="completed", latest_action=event.action_summary, completed_work=[event.output_summary])
                for event in events
            ],
            task_graph=build_default_task_graph(),
            metrics=metrics,
            memory=memory,
            final_output=FinalOutput(
                summary=f"Business Builder Phase 2A local prototype completed for project {active_project_id}.",
                what_was_done=[
                    "Validated the completed Phase 1.1 source handoff.",
                    "Compiled a deterministic local-demo-only safety policy.",
                    f"Created local prototype files under prototypes/{run_id}/.",
                    "Ran technical QA without safe commands or external calls.",
                    "Recorded visual evidence status without installing browser tooling.",
                ],
                recommended_next_actions=["Preview the local prototype and review Phase 2A QA before considering any Phase 2B refinement."],
                generated_artifacts=[artifact.name for artifact in artifact_records],
            ),
            artifacts=artifact_records,
            workspace=WorkspaceSummary(root=project_manager.public_root(active_project_id), files_created=[entry.path for entry in generated_entries], files_edited=[], commands_run=[], command_success=True),
            project_workspace=ProjectWorkspaceSummary(project_id=active_project_id, root=project_workspace.root, files_created=[entry.path for entry in generated_entries], files_edited=[], commands_run=[], command_success=True),
            models_used=["none"],
            project_files_created=[entry.path for entry in generated_entries],
            project_files_updated=[],
            commands_run=[],
            usage_summary={
                "estimated_cost_usd": 0,
                "estimated_tokens": 0,
                "agents_used": len(events),
                "models_used": ["none"],
                "selected_workflow": "business_builder_phase2a_local_prototype",
                "search_needed": False,
                "search_unavailable": False,
                "business_builder": {
                    "phase": "2a",
                    "business_phase": "phase_2a_local_prototype",
                    "status": "local_prototype_completed",
                    "source_run_id": source_run_id,
                    "prototype_mode": "local_demo_only",
                    "personal_data": "not_collected",
                    "external_calls": 0,
                    "public_launch_readiness": {"status": "not_ready"},
                    "preview_route": file_manifest["preview_route"],
                    "prototype_files": file_manifest["generated_files"],
                    "technical_qa": {"status": "passed", "artifact": "prototype_technical_qa.md"},
                    "visual_evidence": {"status": "not_captured", "reason": visual_qa},
                    "actual_provider": "deterministic_local",
                    "actual_model": "none",
                    "live_call_made": False,
                    "provider_call_status": "not_called_deterministic",
                    "external_actions_taken": [],
                    "safe_commands_executed": 0,
                },
            },
            memory_updates=[],
            agent_plan={
                "selected_workflow": "business_builder_phase2a_local_prototype",
                "selected_agents": [
                    {"agent_id": "source_handoff_validator"},
                    {"agent_id": "phase2a_policy_compiler"},
                    {"agent_id": "local_prototype_renderer"},
                    {"agent_id": "technical_qa"},
                    {"agent_id": "visual_evidence_capture"},
                    {"agent_id": "final_prototype_report"},
                ],
                "search_needed": False,
                "search_unavailable": False,
            },
            model_selection={},
        )
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

    def _validate_phase2a_entry(
        self,
        *,
        mode: str,
        project_id: str,
        allow_file_writes: bool,
        allow_safe_commands: bool,
        allow_web_search: bool,
        allow_ceo_live: bool,
        use_memory: bool,
        use_real_coding_agent: bool,
        allow_live_coding_model_call: bool,
        real_coding_dry_run: bool,
        real_coding_model: str | None,
        real_coding_max_files: int | None,
        real_coding_max_repair_attempts: int,
        source_run_id: str | None,
        confirm_local_prototype: bool,
    ) -> None:
        checks = [
            (bool(project_id), "Business Builder Phase 2A requires project_id."),
            (mode == "mock", "Business Builder Phase 2A requires mode=mock."),
            (allow_file_writes, "Business Builder Phase 2A requires allow_file_writes=true."),
            (not allow_safe_commands, "Business Builder Phase 2A requires allow_safe_commands=false."),
            (not allow_web_search, "Business Builder Phase 2A requires allow_web_search=false."),
            (not allow_ceo_live, "Business Builder Phase 2A requires allow_ceo_live=false."),
            (not use_memory, "Business Builder Phase 2A requires use_memory=false."),
            (not use_real_coding_agent, "Business Builder Phase 2A does not allow Real Coding Agent."),
            (not allow_live_coding_model_call, "Business Builder Phase 2A does not allow live coding model calls."),
            (not real_coding_dry_run, "Business Builder Phase 2A does not use coding dry-run."),
            (real_coding_model is None, "Business Builder Phase 2A does not accept a coding model."),
            (real_coding_max_files is None, "Business Builder Phase 2A does not accept coding file limits."),
            (real_coding_max_repair_attempts == 0, "Business Builder Phase 2A does not allow coding repair attempts."),
            (bool(source_run_id and source_run_id.strip()), "Business Builder Phase 2A requires source_run_id."),
            (confirm_local_prototype, "Business Builder Phase 2A requires confirm_local_prototype=true."),
        ]
        for ok, message in checks:
            if not ok:
                raise HTTPException(status_code=422, detail=message)

    def _load_phase2a_source_run(self, source_run_id: str, project_id: str) -> dict[str, Any]:
        source_record = self._get_saved_run(source_run_id)
        if source_record is None:
            raise HTTPException(status_code=404, detail="Business Builder Phase 2A source run was not found.")
        if source_record.status != "completed":
            raise HTTPException(status_code=422, detail="Business Builder Phase 2A source run must be completed.")
        if source_record.run_type != "business_builder":
            raise HTTPException(status_code=422, detail="Business Builder Phase 2A source run must be a business_builder run.")
        if source_record.project_id != project_id:
            raise HTTPException(status_code=422, detail="Business Builder Phase 2A source run must belong to the same project_id.")
        detail = source_record.usage_summary.get("business_builder", {})
        if str(detail.get("phase")) != "1":
            raise HTTPException(status_code=422, detail="Business Builder Phase 2A source run must be a Phase 1.1 planning run.")
        if str(detail.get("planning_version", "")) != "1.1":
            raise HTTPException(status_code=422, detail="Business Builder Phase 2A source run must be Phase 1.1 compatible.")
        artifacts = {artifact.name: artifact for artifact in self.artifacts.list_artifacts(source_run_id)}
        required = {"strategic_decisions.json", "build_handoff.json", "business_builder_state.json"}
        missing = sorted(required - set(artifacts))
        if missing:
            raise HTTPException(status_code=422, detail=f"Business Builder Phase 2A source run is missing artifacts: {', '.join(missing)}.")
        strategic_decisions = self._read_artifact_json(artifacts["strategic_decisions.json"])
        build_handoff = self._read_artifact_json(artifacts["build_handoff.json"])
        state = self._read_artifact_json(artifacts["business_builder_state.json"])
        if state.get("public_launch_readiness", {}).get("status") != "not_ready":
            raise HTTPException(status_code=422, detail="Business Builder Phase 2A source run must keep public launch readiness status as not_ready.")
        if state.get("external_actions_taken"):
            raise HTTPException(status_code=422, detail="Business Builder Phase 2A source run must not have recorded external actions.")
        integrity_parts = []
        for name in sorted(required):
            path = Path(artifacts[name].path)
            integrity_parts.append(f"{name}:{hashlib.sha256(path.read_bytes()).hexdigest()}")
        source_handoff = {
            "source_run_id": source_run_id,
            "source_project_id": project_id,
            "source_planning_version": strategic_decisions.get("planning_version", "1.1"),
            "source_artifact_names": sorted(required),
            "source_handoff_hash_or_integrity_summary": hashlib.sha256("|".join(integrity_parts).encode("utf-8")).hexdigest(),
        }
        return {
            "record": source_record,
            "strategic_decisions": strategic_decisions,
            "build_handoff": build_handoff,
            "state": state,
            "source_handoff": source_handoff,
        }

    def _get_saved_run(self, run_id: str) -> RunRecord | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT payload FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if not row:
            return None
        return RunRecord.model_validate_json(row[0])

    def _read_artifact_json(self, artifact) -> dict[str, Any]:
        try:
            return json.loads(Path(artifact.path).read_text(encoding="utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Business Builder Phase 2A source artifact {artifact.name} is not valid JSON.") from exc

    def _phase2a_policy(self) -> dict[str, Any]:
        return {
            "policy_source": "system_deterministic",
            "prototype_mode": "local_demo_only",
            "personal_data": "not_collected",
            "external_submission": False,
            "external_calls": False,
            "payment": False,
            "orders": False,
            "public_launch": False,
            "trace_note": "System policy narrowed the prototype to local demo-only behavior.",
            "allowed_form_fields": ["interest type", "use-case preference", "plain/flavour preference", "optional fictional sample note"],
            "disallowed_fields": ["name", "nickname", "email", "phone", "city", "area", "address", "contact method", "consent", "payment", "order", "delivery"],
            "canonical_cta": "Save sample interest (demo)",
            "canonical_confirmation": "Demo saved locally. No order was placed, no real personal data was collected, and no external message was sent.",
        }

    def _phase2a_build_spec(self, decisions: dict[str, Any], handoff: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
        positioning = decisions.get("positioning", {})
        website_spec = decisions.get("website_spec", {})
        offer = decisions.get("offer_pricing", {})
        customer = decisions.get("customer_wedge", {})
        safe_products = [
            item
            for item in offer.get("product_status_labels", [])
            if isinstance(item, dict) and not _contains_business_builder_capability(str(item.get("label", "")))
        ][:6]
        if not safe_products:
            safe_products = [{"label": "Plain Greek yogurt concept", "status": "planned", "notes": "Product facts remain pending owner approval."}]
        section_ids = ["header", "hero", "product-concept", "everyday-use", "starter-range", "trust-transparency", "availability-status", "faq", "sample-interest", "footer-disclaimer"]
        faq_topics = _clean_list(website_spec.get("faq_topics", []), limit=5) or ["product status", "pricing status", "availability", "claims policy", "demo form behavior"]
        return {
            "title": "Local Greek Yogurt Prototype",
            "safe_customer_promise": str(positioning.get("safe_customer_promise") or "A thick, simple yogurt option for ordinary breakfast and snack moments, with product details and availability stated only when approved."),
            "primary_launch_segment": str(customer.get("primary_launch_segment") or "local everyday yogurt customers"),
            "primary_use_case": str(customer.get("primary_use_case") or "breakfast and snack moments"),
            "safe_page_sections": section_ids,
            "safe_cta_text": policy["canonical_cta"],
            "safe_faq_themes": faq_topics,
            "approved_product_statuses": safe_products,
            "copy_constraints": [
                "This is a local prototype.",
                "Public availability is not confirmed.",
                "No online orders are accepted.",
                "No payments are accepted.",
                "No real personal data is collected.",
                "No external message is sent.",
            ],
            "prototype_mode": policy["prototype_mode"],
            "form_contract": {
                "allowed_fields": policy["allowed_form_fields"],
                "note_help": "Use a fictional example only. Do not enter real contact or personal information.",
                "button_text": policy["canonical_cta"],
                "confirmation_text": policy["canonical_confirmation"],
                "no_endpoint": True,
                "no_storage": True,
            },
            "disallowed_content": [
                "prices",
                "nutrition values",
                "protein values",
                "ingredients",
                "medical benefits",
                "food-safety claims",
                "certifications",
                "shelf-life claims",
                "delivery promises",
                "reviews",
                "ratings",
                "competitor comparisons",
                "real contact collection",
                "orders",
                "payments",
            ],
            "availability_wording": _phase2a_safe_availability_wording(website_spec.get("safe_availability_wording")),
            "source_handoff_reference": {
                "section_contract_count": len(handoff.get("page_or_section_contracts", [])) if isinstance(handoff, dict) else 0,
                "content_rules_present": bool(isinstance(handoff, dict) and handoff.get("content_rules")),
            },
            "policy_trace_note": policy["trace_note"],
        }

    def _render_phase2a_prototype_files(self, spec: dict[str, Any], policy: dict[str, Any], source_run_id: str, project_id: str, run_id: str) -> dict[str, str]:
        index_html = self._render_phase2a_index_html(spec, policy)
        manifest = {
            "project_id": project_id,
            "phase2a_run_id": run_id,
            "source_run_id": source_run_id,
            "prototype_mode": "local_demo_only",
            "entrypoint": "index.html",
            "generated_files": ["index.html", "README.md", "prototype_manifest.json"],
            "external_calls": 0,
            "personal_data_collected": False,
            "public_launch_allowed": False,
        }
        readme = f"""# Business Builder Phase 2A Local Prototype

This folder contains a deterministic local-only landing-page prototype generated from source planning run `{source_run_id}`.

## Boundaries

- This is a local prototype.
- Public availability is not confirmed.
- No online orders are accepted.
- No payments are accepted.
- No real personal data is collected.
- No external message is sent.

Open `index.html` locally or through the controlled TheHiveMind preview endpoint.
"""
        return {
            "index.html": index_html,
            "README.md": readme,
            "prototype_manifest.json": json.dumps(manifest, indent=2),
        }

    def _render_phase2a_index_html(self, spec: dict[str, Any], policy: dict[str, Any]) -> str:
        title = html.escape(str(spec["title"]))
        promise = html.escape(str(spec["safe_customer_promise"]))
        segment = html.escape(str(spec["primary_launch_segment"]))
        use_case = html.escape(str(spec["primary_use_case"]))
        availability = html.escape(str(spec["availability_wording"]))
        constraints = [html.escape(str(item)) for item in spec["copy_constraints"]]
        products = "\n".join(
            f'<article class="card"><span>{html.escape(str(item.get("status", "planned")))}</span><h3>{html.escape(str(item.get("label", "")))}</h3><p>{html.escape(str(item.get("notes", "Details pending approval.")))}</p></article>'
            for item in spec["approved_product_statuses"]
        )
        faq_items = "\n".join(
            f'<details><summary>{html.escape(str(topic)).title()}</summary><p>This item is shown as a prototype planning topic. Final facts must be approved before public use.</p></details>'
            for topic in spec["safe_faq_themes"]
        )
        disclaimer_items = "\n".join(f"<li>{item}</li>" for item in constraints)
        confirmation = html.escape(policy["canonical_confirmation"])
        note_help = html.escape(spec["form_contract"]["note_help"])
        cta = html.escape(policy["canonical_cta"])
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light; --cream:#fbf6ec; --paper:#fffdf8; --green:#54705b; --mint:#dceadd; --charcoal:#222420; --muted:#666d62; --line:#ddd2bf; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter, Arial, sans-serif; background:var(--cream); color:var(--charcoal); line-height:1.55; }}
    header, main, footer {{ width:min(1120px, calc(100% - 32px)); margin:0 auto; }}
    header {{ display:flex; align-items:center; justify-content:space-between; padding:20px 0; border-bottom:1px solid var(--line); gap:16px; }}
    nav {{ display:flex; gap:14px; flex-wrap:wrap; font-size:13px; }}
    a {{ color:var(--green); text-decoration:none; font-weight:700; }}
    .brand {{ font-weight:900; letter-spacing:.04em; text-transform:uppercase; }}
    .hero {{ display:grid; grid-template-columns:minmax(0, 1.1fr) minmax(280px, .9fr); gap:34px; align-items:center; padding:54px 0 34px; }}
    h1 {{ font-size:clamp(38px, 7vw, 76px); line-height:.96; margin:0 0 18px; letter-spacing:0; }}
    h2 {{ font-size:28px; margin:0 0 12px; }}
    h3 {{ margin:6px 0 8px; }}
    p {{ margin:0 0 12px; }}
    .badge {{ display:inline-block; background:var(--mint); color:#2c5134; border:1px solid #b7d3bb; border-radius:999px; padding:7px 10px; font-size:12px; font-weight:800; margin-bottom:14px; }}
    .button {{ display:inline-block; border:0; background:var(--green); color:white; border-radius:8px; padding:12px 16px; font-weight:800; cursor:pointer; }}
    .secondary {{ background:transparent; color:var(--green); border:1px solid var(--green); margin-left:8px; }}
    .visual {{ min-height:330px; border-radius:16px; background:radial-gradient(circle at 30% 25%, #fff 0 10%, transparent 11%), linear-gradient(135deg, #fff8e9, #dfead8); border:1px solid var(--line); display:grid; place-items:center; text-align:center; padding:28px; }}
    .visual strong {{ font-size:22px; }}
    section {{ padding:28px 0; }}
    .grid {{ display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:14px; }}
    .card, details, form {{ background:var(--paper); border:1px solid var(--line); border-radius:8px; padding:18px; box-shadow:0 8px 24px rgba(70, 54, 30, .05); }}
    .card span {{ color:var(--green); font-size:11px; text-transform:uppercase; font-weight:900; letter-spacing:.08em; }}
    .status {{ border-left:5px solid var(--green); }}
    ul {{ padding-left:20px; }}
    label {{ display:block; font-size:13px; font-weight:800; margin-top:12px; }}
    select, textarea {{ width:100%; margin-top:6px; border:1px solid var(--line); border-radius:8px; background:white; padding:10px; color:var(--charcoal); }}
    textarea {{ min-height:88px; resize:vertical; }}
    .help {{ color:var(--muted); font-size:12px; margin-top:6px; }}
    .confirmation {{ min-height:24px; color:#31593a; font-weight:800; margin-top:12px; }}
    footer {{ border-top:1px solid var(--line); margin-top:24px; padding:26px 0 34px; color:var(--muted); }}
    @media (max-width: 780px) {{ .hero, .grid {{ grid-template-columns:1fr; }} header {{ align-items:flex-start; flex-direction:column; }} h1 {{ font-size:42px; }} }}
  </style>
</head>
<body>
  <header id="header">
    <div class="brand">{title}</div>
    <nav aria-label="Prototype navigation">
      <a href="#product-concept">Concept</a>
      <a href="#starter-range">Starter range</a>
      <a href="#availability-status">Availability</a>
      <a href="#sample-interest">Demo form</a>
    </nav>
  </header>
  <main>
    <section id="hero" class="hero">
      <div>
        <span class="badge">Local prototype only</span>
        <h1>Simple Greek yogurt for everyday routines.</h1>
        <p>{promise}</p>
        <p>This is a local prototype. Public availability is not confirmed.</p>
        <a class="button" href="#sample-interest">Explore the prototype</a>
        <a class="button secondary" href="#availability-status">View availability status</a>
      </div>
      <div class="visual" aria-label="CSS-only product concept placeholder">
        <div><strong>Product visual placeholder</strong><p>Use owner-approved product imagery later.</p></div>
      </div>
    </section>
    <section id="product-concept">
      <h2>Product concept</h2>
      <p>A warm, practical yogurt concept for {segment}. The first use case is {use_case}.</p>
    </section>
    <section id="everyday-use">
      <h2>Everyday use moments</h2>
      <div class="grid">
        <article class="card"><span>breakfast</span><h3>Morning bowls</h3><p>Presented as an example only until product facts are approved.</p></article>
        <article class="card"><span>snacks</span><h3>Simple snack pause</h3><p>Routine use context without health or nutrition claims.</p></article>
        <article class="card"><span>home</span><h3>Shared table moments</h3><p>Plain, practical positioning for feedback before public launch.</p></article>
      </div>
    </section>
    <section id="starter-range">
      <h2>Starter range</h2>
      <div class="grid">{products}</div>
    </section>
    <section id="trust-transparency">
      <h2>Trust and transparency</h2>
      <div class="card"><p>Product details, pricing, availability, claims, and operations remain pending approval. The prototype avoids unsupported claims and records no real customer data.</p></div>
    </section>
    <section id="availability-status">
      <h2>Availability status</h2>
      <div class="card status"><p>{availability}</p><ul>{disclaimer_items}</ul></div>
    </section>
    <section id="faq">
      <h2>FAQ</h2>
      <div class="grid">{faq_items}</div>
    </section>
    <section id="sample-interest">
      <h2>Local demo-only sample-interest form</h2>
      <form id="demo-form">
        <label>Interest type<select><option>General interest</option><option>Product question</option><option>Future feedback</option></select></label>
        <label>Use-case preference<select><option>Breakfast</option><option>Snack</option><option>Home routine</option></select></label>
        <label>Plain/flavour preference<select><option>Plain</option><option>Simple flavour</option><option>Not sure yet</option></select></label>
        <label>Optional fictional sample note<textarea placeholder="Example: A fictional office breakfast use case."></textarea></label>
        <p class="help">{note_help}</p>
        <button class="button" type="submit">{cta}</button>
        <p id="demo-confirmation" class="confirmation" role="status" aria-live="polite"></p>
      </form>
    </section>
  </main>
  <footer id="footer-disclaimer">
    <strong>Prototype disclaimer:</strong> This page is for local review only. No online orders are accepted. No payments are accepted. No real personal data is collected. No external message is sent.
  </footer>
  <script>
    const form = document.getElementById('demo-form');
    const confirmation = document.getElementById('demo-confirmation');
    form.addEventListener('submit', function (event) {{
      event.preventDefault();
      confirmation.textContent = '{confirmation}';
    }});
  </script>
</body>
</html>
"""

    def _phase2a_file_manifest(self, manager: ProjectWorkspaceManager, project_id: str, run_id: str, source_run_id: str, relative_paths: list[str]) -> dict[str, Any]:
        files = []
        for relative_path in relative_paths:
            path = manager.resolve(project_id, relative_path)
            files.append(
                {
                    "path": relative_path,
                    "size_bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
        return {
            "workspace_path": f"{manager.public_root(project_id)}/prototypes/{run_id}",
            "generated_files": files,
            "preview_route": f"/api/projects/{project_id}/prototypes/{run_id}/preview",
            "source_run_id": source_run_id,
        }

    def _phase2a_technical_qa(self, manager: ProjectWorkspaceManager, project_id: str, run_id: str) -> str:
        required_files = ["index.html", "README.md", "prototype_manifest.json"]
        root = manager.resolve(project_id, f"prototypes/{run_id}", allow_directory=True)
        index_path = root / "index.html"
        html_text = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
        checks: list[tuple[str, str]] = []
        checks.append(("PASS" if all((root / name).is_file() for name in required_files) else "BLOCKED", "required prototype files exist"))
        checks.append(("PASS" if html_text.strip() else "BLOCKED", "index.html is non-empty"))
        for section_id in ["header", "hero", "product-concept", "everyday-use", "starter-range", "trust-transparency", "availability-status", "faq", "sample-interest", "footer-disclaimer"]:
            checks.append(("PASS" if f'id="{section_id}"' in html_text else "BLOCKED", f"required section id exists: {section_id}"))
        for text in [
            "This is a local prototype.",
            "Public availability is not confirmed.",
            "No online orders are accepted.",
            "No payments are accepted.",
            "No real personal data is collected.",
            "No external message is sent.",
        ]:
            checks.append(("PASS" if text in html_text else "BLOCKED", f"safety disclaimer present: {text}"))
        lowered = html_text.lower()
        forbidden_checks = {
            "no external URLs": ["http://", "https://", "mailto:", "tel:"],
            "no fetch/XMLHttpRequest/WebSocket": ["fetch(", "xmlhttprequest", "websocket"],
            "no localStorage/sessionStorage": ["localstorage", "sessionstorage"],
            "no form action or backend endpoint": ["<form action", "action=", "/api/"],
            "no unsafe personal-data fields": ['type="email"', 'type="tel"', 'name="name"', 'name="email"', 'name="phone"', 'name="city"', 'name="address"'],
            "no banned transactional CTA text": ["buy now", "order now", "checkout", "register interest", "whatsapp"],
            "no unsafe product or launch claims": ["certified", "protein", "medical", "guaranteed delivery", "customer reviews", "rating"],
        }
        for label, needles in forbidden_checks.items():
            checks.append(("BLOCKED" if any(needle in lowered for needle in needles) else "PASS", label))
        return "# Prototype Technical QA\n\n" + "\n".join(f"- {status}: {message}" for status, message in checks)

    def _phase2a_final_report(self, project_id: str, run_id: str, source_run_id: str, manifest: dict[str, Any], technical_qa: str, visual_qa: str) -> str:
        files = "\n".join(f"- {item['path']} ({item['size_bytes']} bytes)" for item in manifest["generated_files"])
        return f"""# Business Builder Phase 2A Final Prototype Report

## Summary
Created a deterministic local-only landing-page prototype for project `{project_id}` from source planning run `{source_run_id}`.

## Prototype
- Workspace: `{manifest['workspace_path']}`
- Preview: `{manifest['preview_route']}`

## Files
{files}

## Boundaries
- Provider calls: 0
- External actions: 0
- Safe commands: 0
- Real personal data handling: none
- Public launch: not_ready

## Technical QA
{technical_qa}

## Visual Evidence
{visual_qa}
"""

    def _phase2a_event(self, run_id: str, agent_name: str, action_summary: str, output_summary: str, artifact_id: str | None) -> RunEvent:
        return RunEvent(
            timestamp=datetime.now(UTC),
            run_id=run_id,
            agent_name=agent_name,
            agent_role="Business Builder Phase 2A deterministic stage",
            status="completed",
            action_summary=action_summary,
            input_summary="Business Builder Phase 1.1 source handoff plus deterministic Phase 2A local-demo policy.",
            output_summary=output_summary,
            model_used="none",
            provider="deterministic_local",
            estimated_input_tokens=0,
            estimated_output_tokens=0,
            estimated_tokens=0,
            estimated_cost_usd=0,
            estimated_cost=0,
            artifact_id=artifact_id,
        )

    def _phase2a_artifact_agent(self, name: str) -> str:
        if name == "phase2a_source_handoff.json":
            return "Source Handoff Validator"
        if name == "phase2a_policy.json":
            return "Phase 2A Policy Compiler"
        if name in {"phase2a_build_spec.json", "prototype_file_manifest.json"}:
            return "Local Prototype Renderer"
        if name == "prototype_technical_qa.md":
            return "Technical QA"
        if name == "prototype_visual_qa.md":
            return "Visual Evidence Capture"
        return "Final Prototype Report"

    def _business_intake_payload(self, intake: BusinessIntake) -> dict[str, str]:
        return {
            "idea": intake.idea.strip(),
            "business_type": (intake.business_type or "").strip(),
            "market_location": (intake.market_location or "").strip(),
            "target_customer": (intake.target_customer or "").strip(),
            "primary_goal": (intake.primary_goal or "").strip(),
            "budget": (intake.budget or "").strip(),
            "style_preferences": (intake.style_preferences or "").strip(),
            "product_or_service_details": (intake.product_or_service_details or "").strip(),
            "required_features": (intake.required_features or "").strip(),
            "constraints": (intake.constraints or "").strip(),
            "forbidden_actions": (intake.forbidden_actions or "").strip(),
        }

    async def _run_live_business_builder_planner(
        self,
        *,
        command: str,
        project_id: str,
        run_id: str,
        max_cost: float,
        intake: dict[str, str],
        deterministic_bundle: dict[str, Any],
        research_status: dict[str, Any],
        memory_retrieved_count: int,
        artifact_id: str,
    ) -> tuple[dict[str, Any], RunEvent]:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are TheHiveMind Business Planner for Phase 1 only. Return only compact JSON matching the schema. "
                    "Give bounded strategic decisions for the backend to expand into artifacts. Do not write code, do not "
                    "build, do not deploy, do not claim current market facts unless supplied, and do not perform external actions."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "command": command,
                        "business_intake": intake,
                        "research_status": research_status,
                        "memory_status": {"retrieved_count": memory_retrieved_count},
                        "backend_will_generate_artifacts": deterministic_bundle["business_builder_state.json"]["artifact_names"],
                        "phase_1_exclusions": deterministic_bundle["business_brief.json"]["deferred_to_phase_2"],
                        "safety_boundary": "Planning only. build_started=false and build_allowed=false must remain false.",
                        "required_output": "Return concise planning decisions only; no markdown, no prose wrapper, no full artifact package.",
                    },
                    indent=2,
                ),
            },
        ]
        max_output_tokens = self.settings.business_builder_live_max_output_tokens
        input_tokens = estimate_messages_tokens(messages)
        preflight = estimate_cost(self.settings.ceo_model, input_tokens, max_output_tokens, service_tier=None)
        if preflight.estimated_cost_usd > max_cost:
            raise HTTPException(status_code=400, detail=f"Estimated Business Builder planner call ${preflight.estimated_cost_usd:.6f} exceeds request max_cost_usd=${max_cost:.2f}.")
        response, _usage_id = await generate_with_provider(
            provider="openai",
            model=self.settings.ceo_model,
            mode="live",
            messages=messages,
            max_output_tokens=max_output_tokens,
            temperature=0.2,
            service_tier=None,
            run_id=run_id,
            task_id=f"{run_id}:business_builder_live_planning",
            agent_name="Business Planner",
            agent_role="Business Builder Phase 1 strategic planner",
            project_id=project_id,
            request_type="business_builder_live_planning",
            response_format=self._business_builder_decision_response_format(),
            settings=self.settings,
            usage_store=self.usage,
        )
        decision = self._parse_live_business_builder_decision(response.text)
        bundle = self._business_builder_bundle(
            command=command,
            intake=intake,
            allow_web_search=bool(research_status.get("enabled")),
            memory_retrieved_count=memory_retrieved_count,
            research_status=research_status,
            strategic_decisions=decision,
            live_planner={"used": True, "model": self.settings.ceo_model, "output_mode": "strategic_decisions_v1_1"},
        )
        event = RunEvent(
            timestamp=datetime.now(UTC),
            run_id=run_id,
            agent_name="Business Planner",
            agent_role="Business Builder Phase 1 strategic planner",
            status="completed",
            action_summary="Created Business Builder Phase 1 planning package with GPT-5.5 strategic planner",
            input_summary="Compact structured business intake, constraints, search/memory status, artifact contract, and Phase 1 exclusions.",
            output_summary="Validated compact strategy decisions and expanded them into Phase 1 artifacts.",
            model_used=response.model,
            provider=response.provider,
            estimated_input_tokens=response.input_tokens,
            estimated_output_tokens=response.output_tokens,
            estimated_tokens=response.input_tokens + response.output_tokens,
            estimated_cost_usd=response.estimated_cost_usd,
            estimated_cost=response.estimated_cost_usd,
            artifact_id=artifact_id,
        )
        return bundle, event

    def _business_builder_decision_response_format(self) -> dict[str, Any]:
        string_array = {"type": "array", "items": {"type": "string"}}
        product_status = {
            "type": "object",
            "additionalProperties": False,
            "required": ["label", "status", "notes"],
            "properties": {
                "label": {"type": "string"},
                "status": {"type": "string", "enum": ["confirmed", "planned", "exploratory", "unavailable until validated"]},
                "notes": {"type": "string"},
            },
        }
        section_contract = {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "section_id",
                "section_name",
                "purpose",
                "content_order",
                "required_copy_topics",
                "safe_claims_allowed",
                "claims_or_content_forbidden",
                "primary_cta",
                "secondary_cta",
                "status_if_information_is_unknown",
            ],
            "properties": {
                "section_id": {"type": "string"},
                "section_name": {"type": "string"},
                "purpose": {"type": "string"},
                "content_order": string_array,
                "required_copy_topics": string_array,
                "safe_claims_allowed": string_array,
                "claims_or_content_forbidden": string_array,
                "primary_cta": {"type": "string"},
                "secondary_cta": {"type": "string"},
                "status_if_information_is_unknown": {"type": "string"},
            },
        }
        readiness = {
            "type": "object",
            "additionalProperties": False,
            "required": ["status", "ready_when", "blockers", "allowed_scope", "exclusions", "approved_placeholder_policy"],
            "properties": {
                "status": {"type": "string"},
                "ready_when": string_array,
                "blockers": string_array,
                "allowed_scope": string_array,
                "exclusions": string_array,
                "approved_placeholder_policy": {"type": "string"},
            },
        }
        public_readiness = {
            "type": "object",
            "additionalProperties": False,
            "required": ["status", "blockers", "evidence_required", "operational_requirements", "external_action_approvals_required"],
            "properties": {
                "status": {"type": "string"},
                "blockers": string_array,
                "evidence_required": string_array,
                "operational_requirements": string_array,
                "external_action_approvals_required": string_array,
            },
        }
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "planning_version",
                "customer_wedge",
                "positioning",
                "validation_plan",
                "offer_pricing",
                "brand",
                "website_spec",
                "inquiry_flow",
                "readiness",
            ],
            "properties": {
                "planning_version": {"type": "string"},
                "customer_wedge": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["primary_launch_segment", "secondary_segments", "why_primary_segment_first", "primary_use_case", "main_customer_job", "main_objections", "customer_validation_needed"],
                    "properties": {
                        "primary_launch_segment": {"type": "string"},
                        "secondary_segments": string_array,
                        "why_primary_segment_first": {"type": "string"},
                        "primary_use_case": {"type": "string"},
                        "main_customer_job": {"type": "string"},
                        "main_objections": string_array,
                        "customer_validation_needed": string_array,
                    },
                },
                "positioning": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["positioning_statement", "safe_customer_promise", "differentiation_hypotheses", "what_the_brand_is_not", "safe_message_pillars", "unsupported_claims_to_avoid"],
                    "properties": {
                        "positioning_statement": {"type": "string"},
                        "safe_customer_promise": {"type": "string"},
                        "differentiation_hypotheses": string_array,
                        "what_the_brand_is_not": string_array,
                        "safe_message_pillars": string_array,
                        "unsupported_claims_to_avoid": string_array,
                    },
                },
                "validation_plan": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["validation_goal", "highest_risk_assumptions", "interview_or_feedback_target", "recommended_validation_questions", "positive_signals", "negative_signals", "decision_rules", "what_to_change_if_validation_is_weak"],
                    "properties": {
                        "validation_goal": {"type": "string"},
                        "highest_risk_assumptions": string_array,
                        "interview_or_feedback_target": {"type": "string"},
                        "recommended_validation_questions": string_array,
                        "positive_signals": string_array,
                        "negative_signals": string_array,
                        "decision_rules": string_array,
                        "what_to_change_if_validation_is_weak": string_array,
                    },
                },
                "offer_pricing": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["anchor_offer", "exploratory_variants", "product_status_labels", "customer_value_hypotheses", "pricing_inputs_required", "pricing_validation_questions", "trial_offer_framework", "future_repeat_purchase_framework", "explicitly_unknown"],
                    "properties": {
                        "anchor_offer": {"type": "string"},
                        "exploratory_variants": string_array,
                        "product_status_labels": {"type": "array", "items": product_status},
                        "customer_value_hypotheses": string_array,
                        "pricing_inputs_required": string_array,
                        "pricing_validation_questions": string_array,
                        "trial_offer_framework": {"type": "string"},
                        "future_repeat_purchase_framework": {"type": "string"},
                        "explicitly_unknown": string_array,
                    },
                },
                "brand": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["brand_principles", "tone_of_voice", "say_examples", "avoid_examples", "visual_hierarchy", "photography_or_illustration_direction", "trust_cues_allowed", "trust_cues_not_allowed", "design_anti_patterns"],
                    "properties": {
                        "brand_principles": string_array,
                        "tone_of_voice": {"type": "string"},
                        "say_examples": string_array,
                        "avoid_examples": string_array,
                        "visual_hierarchy": string_array,
                        "photography_or_illustration_direction": {"type": "string"},
                        "trust_cues_allowed": string_array,
                        "trust_cues_not_allowed": string_array,
                        "design_anti_patterns": string_array,
                    },
                },
                "website_spec": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["homepage_objective", "section_order", "section_contracts", "placeholder_policy", "safe_availability_wording", "cta_wording_direction", "faq_topics", "system_must_never_invent"],
                    "properties": {
                        "homepage_objective": {"type": "string"},
                        "section_order": string_array,
                        "section_contracts": {"type": "array", "items": section_contract},
                        "placeholder_policy": {"type": "string"},
                        "safe_availability_wording": {"type": "string"},
                        "cta_wording_direction": {"type": "string"},
                        "faq_topics": string_array,
                        "system_must_never_invent": string_array,
                    },
                },
                "inquiry_flow": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["inquiry_purpose", "allowed_inquiry_types", "fields", "required_vs_optional_fields", "local_only_behavior", "storage_behavior", "success_state", "error_state", "privacy_or_data_handling_placeholder", "non_goals"],
                    "properties": {
                        "inquiry_purpose": {"type": "string"},
                        "allowed_inquiry_types": string_array,
                        "fields": string_array,
                        "required_vs_optional_fields": string_array,
                        "local_only_behavior": {"type": "string"},
                        "storage_behavior": {"type": "string"},
                        "success_state": {"type": "string"},
                        "error_state": {"type": "string"},
                        "privacy_or_data_handling_placeholder": {"type": "string"},
                        "non_goals": string_array,
                    },
                },
                "readiness": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["local_build_readiness", "public_launch_readiness"],
                    "properties": {
                        "local_build_readiness": readiness,
                        "public_launch_readiness": public_readiness,
                    },
                },
            },
        }
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "business_builder_phase1_decisions",
                "strict": True,
                "schema": schema,
            },
        }

    def _parse_live_business_builder_decision(self, text: str) -> dict[str, Any]:
        payload = self._parse_json_object(text, label="Business Builder live planner")
        return self._validate_business_builder_decisions(payload, source="live")

    def _validate_business_builder_decisions(self, payload: dict[str, Any], *, source: str) -> dict[str, Any]:
        groups = {
            "customer_wedge": ["primary_launch_segment", "secondary_segments", "why_primary_segment_first", "primary_use_case", "main_customer_job", "main_objections", "customer_validation_needed"],
            "positioning": ["positioning_statement", "safe_customer_promise", "differentiation_hypotheses", "what_the_brand_is_not", "safe_message_pillars", "unsupported_claims_to_avoid"],
            "validation_plan": ["validation_goal", "highest_risk_assumptions", "interview_or_feedback_target", "recommended_validation_questions", "positive_signals", "negative_signals", "decision_rules", "what_to_change_if_validation_is_weak"],
            "offer_pricing": ["anchor_offer", "exploratory_variants", "product_status_labels", "customer_value_hypotheses", "pricing_inputs_required", "pricing_validation_questions", "trial_offer_framework", "future_repeat_purchase_framework", "explicitly_unknown"],
            "brand": ["brand_principles", "tone_of_voice", "say_examples", "avoid_examples", "visual_hierarchy", "photography_or_illustration_direction", "trust_cues_allowed", "trust_cues_not_allowed", "design_anti_patterns"],
            "website_spec": ["homepage_objective", "section_order", "section_contracts", "placeholder_policy", "safe_availability_wording", "cta_wording_direction", "faq_topics", "system_must_never_invent"],
            "inquiry_flow": ["inquiry_purpose", "allowed_inquiry_types", "fields", "required_vs_optional_fields", "local_only_behavior", "storage_behavior", "success_state", "error_state", "privacy_or_data_handling_placeholder", "non_goals"],
            "readiness": ["local_build_readiness", "public_launch_readiness"],
        }
        for group, fields in groups.items():
            if not isinstance(payload.get(group), dict):
                raise HTTPException(status_code=502, detail=f"Business Builder {source} strategic decisions missing object: {group}.")
            missing = [field for field in fields if field not in payload[group]]
            if missing:
                raise HTTPException(status_code=502, detail=f"Business Builder {source} strategic decisions missing {group} fields: {', '.join(missing)}.")

        payload["planning_version"] = str(payload.get("planning_version") or "1.1")
        if payload["planning_version"] != "1.1":
            payload["planning_version"] = "1.1"

        for group in ("customer_wedge", "positioning", "validation_plan", "offer_pricing", "brand", "website_spec", "inquiry_flow"):
            payload[group] = _clean_decision_value(payload[group])

        product_status_labels = []
        allowed_product_statuses = {"confirmed", "planned", "exploratory", "unavailable until validated"}
        for item in payload["offer_pricing"].get("product_status_labels", []):
            if not isinstance(item, dict) or not str(item.get("label", "")).strip():
                continue
            status = str(item.get("status", "")).strip()
            if status not in allowed_product_statuses:
                raise HTTPException(status_code=502, detail=f"Business Builder {source} strategic decisions product status has invalid status: {status or '<blank>'}.")
            product_status_labels.append(
                {
                    "label": str(item.get("label", "")).strip(),
                    "status": status,
                    "notes": str(item.get("notes", "")).strip(),
                }
            )
        payload["offer_pricing"]["product_status_labels"] = product_status_labels[:8]
        if not payload["offer_pricing"]["product_status_labels"]:
            raise HTTPException(status_code=502, detail=f"Business Builder {source} strategic decisions require at least one product status label.")

        payload["website_spec"]["section_contracts"] = [
            self._normalize_section_contract(item)
            for item in payload["website_spec"].get("section_contracts", [])
            if isinstance(item, dict) and str(item.get("section_id", "")).strip()
        ]
        if len(payload["website_spec"]["section_contracts"]) < 5:
            raise HTTPException(status_code=502, detail=f"Business Builder {source} strategic decisions require at least five website section contracts.")

        if len(payload["validation_plan"].get("recommended_validation_questions", [])) < 5:
            raise HTTPException(status_code=502, detail=f"Business Builder {source} strategic decisions require at least five validation questions.")
        if len(payload["validation_plan"].get("positive_signals", [])) < 3 or len(payload["validation_plan"].get("negative_signals", [])) < 3:
            raise HTTPException(status_code=502, detail=f"Business Builder {source} strategic decisions require at least three positive and three negative validation signals.")
        if not str(payload["customer_wedge"].get("primary_launch_segment", "")).strip():
            raise HTTPException(status_code=502, detail=f"Business Builder {source} strategic decisions require one primary launch segment.")

        local = payload["readiness"]["local_build_readiness"]
        public = payload["readiness"]["public_launch_readiness"]
        if not isinstance(local, dict) or not isinstance(public, dict):
            raise HTTPException(status_code=502, detail=f"Business Builder {source} strategic decisions require readiness objects.")
        local_schema_fields = ("status", "ready_when", "blockers", "allowed_scope", "exclusions", "approved_placeholder_policy")
        canonical_local_fields = ("status", "policy_source", "ready_when", "local_build_blockers", "open_content_assumptions", "allowed_future_phase_2_scope", "exclusions")
        if not all(field in local for field in local_schema_fields) and not all(field in local for field in canonical_local_fields):
            missing_local = [field for field in local_schema_fields if field not in local]
            raise HTTPException(status_code=502, detail=f"Business Builder {source} strategic decisions missing local readiness fields: {', '.join(missing_local)}.")
        missing_public = [field for field in ("status", "blockers", "evidence_required", "operational_requirements", "external_action_approvals_required") if field not in public]
        if missing_public:
            raise HTTPException(status_code=502, detail=f"Business Builder {source} strategic decisions missing public readiness fields: {', '.join(missing_public)}.")
        public["status"] = "not_ready"
        for readiness in (local, public):
            for key, value in list(readiness.items()):
                if isinstance(value, list):
                    readiness[key] = _clean_list(value, limit=12)
                elif isinstance(value, str):
                    readiness[key] = value.strip()

        return self._apply_business_builder_system_policy(payload)

    def _apply_business_builder_system_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        notes: list[str] = []

        product_status_labels = []
        removed_capabilities = []
        for item in payload["offer_pricing"].get("product_status_labels", []):
            label = str(item.get("label", "")).strip()
            if _contains_business_builder_capability(label):
                removed_capabilities.append(label)
                continue
            product_status_labels.append(item)
        if removed_capabilities:
            notes.append("System policy removed operational capabilities from product status labels.")
        if not product_status_labels:
            anchor = str(payload["offer_pricing"].get("anchor_offer", "")).strip()
            if anchor and not _contains_business_builder_capability(anchor):
                product_status_labels.append({"label": anchor, "status": "planned", "notes": "Derived from planner anchor offer after system policy removed non-product capability labels."})
                notes.append("System policy derived the product status from the anchor offer because capability labels were excluded.")
        payload["offer_pricing"]["product_status_labels"] = product_status_labels

        original_inquiry_text = json.dumps(payload.get("inquiry_flow", {})).lower()
        if _contains_business_builder_personal_data_field(original_inquiry_text) or _contains_real_inquiry_claim(original_inquiry_text):
            notes.append("System policy narrowed the local prototype handoff to demo-only behavior.")
        payload["inquiry_flow"] = _canonical_business_builder_inquiry_flow()

        original_cta = str(payload.get("website_spec", {}).get("cta_wording_direction", ""))
        if _contains_real_cta(original_cta):
            notes.append("System policy replaced local prototype CTA wording with demo-only wording.")
        payload["website_spec"]["cta_wording_direction"] = _canonical_business_builder_cta_wording()
        for contract in payload["website_spec"].get("section_contracts", []):
            if _contains_real_cta(f"{contract.get('primary_cta', '')} {contract.get('secondary_cta', '')}"):
                contract["primary_cta"] = "Explore the prototype"
                contract["secondary_cta"] = "View availability status"

        original_local = payload["readiness"].get("local_build_readiness", {})
        original_local_text = json.dumps(original_local).lower()
        if (
            str(original_local.get("status", "")).strip() != "conditionally_ready"
            or _contains_local_blocker_misclassification(original_local.get("blockers", []))
            or "website build" in original_local_text
        ):
            notes.append("System policy replaced planner local readiness with canonical Phase 1 demo-only readiness.")
        payload["readiness"]["local_build_readiness"] = _canonical_business_builder_local_readiness()
        payload["readiness"]["public_launch_readiness"]["status"] = "not_ready"

        payload["policy_boundary_notes"] = _dedupe_list(notes)
        return payload

    def _normalize_section_contract(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "section_id": str(item.get("section_id", "")).strip(),
            "section_name": str(item.get("section_name", "")).strip(),
            "purpose": str(item.get("purpose", "")).strip(),
            "content_order": _clean_list(item.get("content_order", []), limit=8),
            "required_copy_topics": _clean_list(item.get("required_copy_topics", []), limit=8),
            "safe_claims_allowed": _clean_list(item.get("safe_claims_allowed", []), limit=8),
            "claims_or_content_forbidden": _clean_list(item.get("claims_or_content_forbidden", []), limit=8),
            "primary_cta": str(item.get("primary_cta", "")).strip(),
            "secondary_cta": str(item.get("secondary_cta", "")).strip(),
            "status_if_information_is_unknown": str(item.get("status_if_information_is_unknown", "")).strip(),
        }

    def _parse_json_object(self, text: str, *, label: str) -> dict[str, Any]:
        cleaned = (text or "").strip()
        if not cleaned:
            raise HTTPException(status_code=502, detail=f"{label} returned empty output instead of JSON.")
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("` \n")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                try:
                    payload = json.loads(cleaned[start : end + 1])
                except json.JSONDecodeError:
                    preview = cleaned[:300].replace("\n", " ")
                    raise HTTPException(status_code=502, detail=f"{label} returned malformed JSON: {exc.msg}. Preview: {preview}") from exc
            else:
                preview = cleaned[:300].replace("\n", " ")
                raise HTTPException(status_code=502, detail=f"{label} returned malformed JSON: {exc.msg}. Preview: {preview}") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=502, detail=f"{label} returned JSON that was not an object.")
        return payload

    def _business_builder_event(
        self,
        *,
        run_id: str,
        mode: str,
        agent_name: str,
        agent_role: str,
        model: str,
        provider: str,
        input_text: str,
        output_text: str,
        action_summary: str,
        artifact_id: str,
        estimated_model: str | None = None,
    ) -> RunEvent:
        cost_model = estimated_model or model
        input_tokens = estimate_tokens(input_text)
        output_tokens = estimate_tokens(output_text)
        service_tier = None if agent_name == "Business Planner" and cost_model == self.settings.ceo_model else self.settings.ceo_service_tier if cost_model == self.settings.ceo_model else None
        cost = estimate_cost(cost_model, input_tokens, output_tokens, service_tier=service_tier).estimated_cost_usd
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
            provider=provider,
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=output_tokens,
            estimated_tokens=input_tokens + output_tokens,
            estimated_cost_usd=cost,
            estimated_cost=cost,
            artifact_id=artifact_id or None,
        )

    def _mock_business_builder_decisions(self, intake: dict[str, str]) -> dict[str, Any]:
        primary_segment = "working adults who want a simple breakfast or snack option"
        if intake["target_customer"]:
            primary_segment = "working adults within the supplied broad audience, selected as an assumption for first validation"
        secondary_segments = ["urban families", "university students", "health-conscious adults"]
        forbidden_claims = [
            "specific protein or nutrition claims",
            "medical, dietary, weight-loss, or fitness claims",
            "food-safety, certification, shelf-life, or compliance claims",
            "Pakistani market prices or demand figures",
            "supplier, delivery, or availability guarantees",
            "reviews, testimonials, or competitor comparisons",
        ]
        section_contracts = [
            self._section_contract(
                "hero",
                "Hero",
                "Make the offer understandable without unsupported claims.",
                ["Business name or offer category", "safe promise", "availability caveat", "manual-interest CTA"],
                ["plain description", "current planning status", "manual review wording"],
                forbidden_claims,
                "Explore the prototype",
                "Read product details",
                "Show a clearly labelled placeholder if product facts are not approved.",
            ),
            self._section_contract(
                "everyday_use",
                "Everyday Use Moments",
                "Help visitors imagine safe use contexts without health claims.",
                ["breakfast use", "snack use", "home routine use"],
                ["use occasions supplied or clearly framed as examples"],
                forbidden_claims,
                "See possible uses",
                "Review assumptions",
                "Mark examples as validation hypotheses.",
            ),
            self._section_contract(
                "offer_preview",
                "Offer / Product Preview",
                "Show confirmed, planned, and exploratory products separately.",
                ["anchor offer", "exploratory variants", "status labels", "unknowns"],
                ["plain/flavour status", "unknown pricing and availability"],
                forbidden_claims,
                "View offer status",
                "Ask a question locally",
                "Use unavailable-until-validated labels.",
            ),
            self._section_contract(
                "trust_transparency",
                "Trust And Transparency",
                "Explain what is known, unknown, and approval-gated.",
                ["facts from owner", "assumptions", "claims avoided", "approval needs"],
                ["transparent caveats", "manual review boundaries"],
                forbidden_claims,
                "Review transparency notes",
                "Read FAQ",
                "Say facts are pending owner approval.",
            ),
            self._section_contract(
                "availability_status",
                "Availability Status",
                "Avoid pretending the business can currently sell or deliver.",
                ["current phase", "not accepting orders", "future manually reviewed inquiry"],
                ["planning-only availability wording"],
                forbidden_claims,
                "Check future availability",
                "Join local interest list",
                "Use planning-only wording until operations are approved.",
            ),
            self._section_contract(
                "faq",
                "FAQ",
                "Answer safe basic questions and route unknowns to placeholders.",
                ["product status", "pricing status", "claims policy", "future inquiry behavior"],
                ["known facts", "explicit unknowns"],
                forbidden_claims,
                "Read FAQ",
                "Submit local interest",
                "Use 'to be confirmed' for unknowns.",
            ),
            self._section_contract(
                "manual_inquiry",
                "Manual Inquiry",
                "Define a local-only non-production interest form.",
                ["purpose", "fields", "local storage", "privacy placeholder", "non-goals"],
                ["local mock behavior", "no external submission"],
                forbidden_claims + ["email or WhatsApp submission claims", "payment or order acceptance"],
                "Save sample interest (demo)",
                "Clear form",
                "State that no order is placed, no real personal data is collected, and no external message is sent.",
            ),
            self._section_contract(
                "footer_disclaimer",
                "Footer / Disclaimer",
                "Keep boundaries visible across the page.",
                ["planning status", "claims disclaimer", "external action exclusions"],
                ["Phase 1 planning-only disclaimer"],
                forbidden_claims,
                "Review scope",
                "Back to top",
                "Use persistent planning-only disclaimer.",
            ),
        ]
        decisions = {
            "planning_version": "1.1",
            "customer_wedge": {
                "primary_launch_segment": primary_segment,
                "secondary_segments": secondary_segments,
                "why_primary_segment_first": "This segment gives a narrow daily-use wedge to validate before treating families, students, and health-focused buyers as equal primary audiences.",
                "primary_use_case": "A convenient plain yogurt option for routine breakfast or snack moments.",
                "main_customer_job": "Understand whether the product fits an everyday routine and whether it feels trustworthy enough to try later.",
                "main_objections": ["price is unknown", "availability is unknown", "claims need evidence", "taste and texture are unproven"],
                "customer_validation_needed": ["confirm the first customer wedge", "validate use occasion", "validate offer clarity", "validate willingness to make a future inquiry"],
            },
            "positioning": {
                "positioning_statement": "A warm local Greek yogurt concept for simple everyday breakfast and snack routines, intentionally kept small until operations and claims are validated.",
                "safe_customer_promise": "A thick, simple yogurt option for ordinary breakfast and snack moments, with product details and availability stated only when approved.",
                "differentiation_hypotheses": ["simpler wording than fitness-style yogurt brands", "local and practical tone", "transparent status labels for what is confirmed versus exploratory"],
                "what_the_brand_is_not": ["medical or diet brand", "gym-supplement brand", "luxury premium dessert brand", "instant delivery or subscription service"],
                "safe_message_pillars": ["simple everyday use", "transparent product status", "manual review before orders", "claims only after approval"],
                "unsupported_claims_to_avoid": forbidden_claims,
            },
            "validation_plan": {
                "validation_goal": "Decide whether the first local website prototype should focus on one everyday-use segment and a small plain-yogurt-led offer.",
                "highest_risk_assumptions": ["the primary segment is correct", "plain yogurt is a credible anchor offer", "visitors understand that ordering is not yet live", "trust copy can work without unsupported claims"],
                "interview_or_feedback_target": "Small manually selected feedback group from the assumed primary segment; no outreach is performed by Phase 1.",
                "recommended_validation_questions": [
                    "When would you actually consider using this yogurt in a normal week?",
                    "What would make the offer clear enough to remember?",
                    "Which product facts would you need before trusting the brand?",
                    "Which flavour or plain option would you want validated first?",
                    "What wording feels honest versus exaggerated?",
                    "Would a local interest form feel useful before ordering exists?",
                    "What would make you decide this is not for you?",
                ],
                "positive_signals": ["users can explain the offer back in one sentence", "users pick one likely use moment", "users ask practical product questions instead of doubting the premise"],
                "negative_signals": ["users expect health claims or nutrition proof before caring", "users cannot distinguish planned from available products", "users only respond to delivery or price promises that are not approved"],
                "decision_rules": [
                    "Keep the initial offer if the primary segment understands the plain-yogurt-led concept and asks for practical next facts.",
                    "Narrow the segment if feedback differs strongly between families, students, and working adults.",
                    "Change the offer if plain yogurt does not create interest without unsupported nutrition claims.",
                    "Do not make public claims until product, pricing, operations, and compliance evidence is approved.",
                ],
                "what_to_change_if_validation_is_weak": ["narrow to a smaller use case", "remove flavours until plain offer is clear", "replace broad trust copy with more concrete owner-approved facts"],
            },
            "offer_pricing": {
                "anchor_offer": "Plain thick Greek yogurt as the first validation anchor, with all product details subject to owner approval.",
                "exploratory_variants": ["simple flavour options"],
                "product_status_labels": [
                    {"label": "Plain Greek yogurt", "status": "planned", "notes": "Owner supplied the idea, but product facts still need approval."},
                    {"label": "Simple flavoured options", "status": "exploratory", "notes": "Mention only as possible variants until validated."},
                ],
                "customer_value_hypotheses": ["simple everyday option", "trustworthy local presentation", "clear manual inquiry path later"],
                "pricing_inputs_required": ["production cost", "packaging cost", "approved product size", "delivery/collection method", "compliance and storage constraints"],
                "pricing_validation_questions": ["What price information would you need before considering it?", "Would you compare it to snacks, breakfast items, or desserts?", "Would a trial quantity make sense before repeat purchase?"],
                "trial_offer_framework": "A future trial offer may be described only as manually reviewed and only after product facts, costs, and claims are approved.",
                "future_repeat_purchase_framework": "A repeat purchase path remains later-stage and depends on production, storage, delivery, and demand validation.",
                "explicitly_unknown": ["final price", "pack size", "nutrition facts", "shelf life", "supplier", "delivery area", "availability date"],
            },
            "brand": {
                "brand_principles": ["warm", "clean", "modern", "trustworthy", "simple", "local", "practical"],
                "tone_of_voice": "Plainspoken, careful, friendly, and transparent about what is known versus still being validated.",
                "say_examples": ["Simple Greek yogurt for everyday routines.", "Availability and product details are being validated.", "Future inquiries will be manually reviewed."],
                "avoid_examples": ["High-protein health fix.", "Certified safest yogurt.", "Best price in Pakistan.", "Doctors recommend it.", "Order now for guaranteed delivery."],
                "visual_hierarchy": ["clear offer headline", "short safe promise", "status labels", "product preview", "trust/FAQ", "manual inquiry"],
                "photography_or_illustration_direction": "Use real approved product/process imagery later; Phase 1 creates no images or mockups.",
                "trust_cues_allowed": ["owner-approved facts", "transparent unknowns", "manual review language", "clear product status labels"],
                "trust_cues_not_allowed": ["fake reviews", "unverified certifications", "medical cues", "nutrition badges without evidence", "luxury-premium exaggeration"],
                "design_anti_patterns": ["medical branding", "gym-supplement look", "fake testimonials", "overly luxury presentation", "claim-heavy hero"],
            },
            "website_spec": {
                "homepage_objective": "Explain the business concept safely and prepare for a future local mock MVP without implying public launch readiness.",
                "section_order": [contract["section_id"] for contract in section_contracts],
                "section_contracts": section_contracts,
                "placeholder_policy": "Unknown product, pricing, delivery, certification, nutrition, supplier, and availability facts must use labelled placeholders or be omitted.",
                "safe_availability_wording": "Planning-stage concept; products, pricing, and availability are not yet final or public.",
                "cta_wording_direction": "Use demo/prototype language such as Explore the prototype, Save sample interest (demo), or View availability status. Do not use real signup, order, payment, or delivery language.",
                "faq_topics": ["product status", "pricing status", "claims policy", "availability", "manual inquiry behavior", "privacy placeholder"],
                "system_must_never_invent": forbidden_claims,
            },
            "inquiry_flow": {
                "inquiry_purpose": "Future local-only interest capture for prototype validation, not a real order or external message.",
                "allowed_inquiry_types": ["general interest", "product question", "flavour preference"],
                "fields": ["fictional sample name", "fictional sample area", "interest type", "sample message"],
                "required_vs_optional_fields": ["required demo fields: interest type and sample message", "optional demo fields: fictional sample name and fictional sample area"],
                "local_only_behavior": "Default Phase 2 scope is a local mock form with no external submission and no real contact-detail collection.",
                "storage_behavior": "If implemented later, store fictional/sample local demo data only. Do not request or store real contact details.",
                "success_state": "Demo saved locally. No order was placed, no real personal data was collected, and no external message was sent.",
                "error_state": "Show local validation errors for missing required fields.",
                "privacy_or_data_handling_placeholder": "Display demo-only wording that asks users to use fictional/sample values until a real privacy policy is approved.",
                "non_goals": ["email", "WhatsApp", "CRM", "payment", "delivery", "analytics", "real order acceptance"],
            },
            "readiness": {
                "local_build_readiness": {
                    "status": "conditionally_ready",
                    "ready_when": ["owner accepts placeholder policy", "Phase 2 local prototype is explicitly requested", "no public claims or integrations are requested"],
                    "blockers": ["owner has not accepted the placeholder policy", "Phase 2 local prototype has not been explicitly requested", "public claims or integrations are being requested"],
                    "approved_placeholder_policy": "Use labelled placeholders and status labels for unresolved product facts, pricing, and availability instead of treating them as local-build blockers.",
                    "allowed_scope": ["local non-deployed landing page", "static content sections", "local mock interest form", "sample FAQ"],
                    "exclusions": ["deployment", "payments", "real orders", "external messaging", "analytics", "public claims"],
                },
                "public_launch_readiness": {
                    "status": "not_ready",
                    "blockers": ["pricing unresolved", "product facts unresolved", "operations unresolved", "compliance/food-safety claims unapproved", "no external-action approvals"],
                    "evidence_required": ["approved product facts", "pricing", "production and storage details", "delivery/collection policy", "compliance/legal review", "claim evidence"],
                    "operational_requirements": ["supplier/production plan", "fulfillment process", "customer support process", "privacy/data handling", "refund/cancellation policy if applicable"],
                    "external_action_approvals_required": ["deployment", "domain/hosting", "payments", "email/WhatsApp", "supplier/customer outreach", "ads/social posting", "analytics"],
                },
            },
        }
        return self._validate_business_builder_decisions(decisions, source="mock")

    def _section_contract(
        self,
        section_id: str,
        section_name: str,
        purpose: str,
        content_order: list[str],
        safe_claims_allowed: list[str],
        claims_or_content_forbidden: list[str],
        primary_cta: str,
        secondary_cta: str,
        status_if_information_is_unknown: str,
    ) -> dict[str, Any]:
        return {
            "section_id": section_id,
            "section_name": section_name,
            "purpose": purpose,
            "content_order": content_order,
            "required_copy_topics": content_order,
            "safe_claims_allowed": safe_claims_allowed,
            "claims_or_content_forbidden": claims_or_content_forbidden,
            "primary_cta": primary_cta,
            "secondary_cta": secondary_cta,
            "status_if_information_is_unknown": status_if_information_is_unknown,
        }

    def _business_builder_bundle(
        self,
        *,
        command: str,
        intake: dict[str, str],
        allow_web_search: bool,
        memory_retrieved_count: int,
        research_status: dict[str, Any] | None = None,
        strategic_decisions: dict[str, Any] | None = None,
        live_planner: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        strategic_decisions = strategic_decisions or self._mock_business_builder_decisions(intake)
        customer = strategic_decisions["customer_wedge"]
        positioning = strategic_decisions["positioning"]
        validation = strategic_decisions["validation_plan"]
        offer = strategic_decisions["offer_pricing"]
        brand = strategic_decisions["brand"]
        website = strategic_decisions["website_spec"]
        inquiry = strategic_decisions["inquiry_flow"]
        readiness = strategic_decisions["readiness"]
        facts = [f"Business idea: {intake['idea']}"]
        for label, key in (
            ("Business type", "business_type"),
            ("Market/location", "market_location"),
            ("Target customer", "target_customer"),
            ("Primary goal", "primary_goal"),
            ("Budget", "budget"),
            ("Style preferences", "style_preferences"),
            ("Product/service details", "product_or_service_details"),
            ("Required features", "required_features"),
        ):
            if intake[key]:
                facts.append(f"{label}: {intake[key]}")
        assumptions = [
            "The first MVP should be small, informational, and approval-gated before any customer-facing operations.",
            "Pricing, operations, compliance, delivery, and claims require human evidence or approval before launch.",
        ]
        if not intake["target_customer"]:
            assumptions.append("Target customer details are not fully supplied and must be validated before Phase 2.")
        if not intake["budget"]:
            assumptions.append("No final budget was supplied; budget remains an unresolved decision.")
        constraints = self._split_business_lines(intake["constraints"]) or ["No unsupported claims or external actions in Phase 1."]
        forbidden_actions = self._split_business_lines(intake["forbidden_actions"])
        blocked_actions = list(
            dict.fromkeys(
                [
                "deployments",
                "domain_purchase",
                "hosting_purchase",
                "package_installation",
                "cloud_setup",
                "payments",
                "email",
                "whatsapp",
                "social_media_posting",
                "ads",
                "supplier_contact",
                "customer_contact",
                "external_apis",
                *forbidden_actions,
                ]
            )
        )
        approvals_needed = [
            "Approve or revise assumptions before Phase 2.",
            "Approve product claims, pricing, compliance, operations, and integrations before launch.",
        ]
        approvals_needed = _dedupe_list([*approvals_needed, *readiness["public_launch_readiness"]["external_action_approvals_required"]])
        assumptions = _dedupe_list([*assumptions, *validation["highest_risk_assumptions"]])
        deferred = [
            "Phase 2 website/app implementation",
            "Visual assets, logo, images, and screenshots",
            "Checkout, payments, messaging, delivery, and external integrations",
            "Deployments, hosting, domains, ads, and outreach",
        ]
        research_status = research_status or {"enabled": bool(allow_web_search), "used": False, "source_count": 0}
        brief = {
            "schema_version": "1.0",
            "planning_version": "1.1",
            "phase": 1,
            "status": "planning_complete_not_built",
            "intake": intake,
            "facts_from_user": facts,
            "strategic_decisions_summary": {
                "primary_launch_segment": customer["primary_launch_segment"],
                "safe_customer_promise": positioning["safe_customer_promise"],
                "anchor_offer": offer["anchor_offer"],
                "local_build_readiness_status": readiness["local_build_readiness"]["status"],
                "public_launch_readiness_status": readiness["public_launch_readiness"]["status"],
            },
            "primary_launch_segment": customer["primary_launch_segment"],
            "secondary_segments": customer["secondary_segments"],
            "local_build_readiness": readiness["local_build_readiness"],
            "public_launch_readiness": readiness["public_launch_readiness"],
            "assumptions": assumptions,
            "research_status": research_status,
            "memory_status": {"retrieval_enabled": memory_retrieved_count > 0, "retrieved_count": memory_retrieved_count},
            "constraints": constraints,
            "forbidden_actions": forbidden_actions,
            "approvals_needed": approvals_needed,
            "deferred_to_phase_2": deferred,
        }
        if live_planner:
            brief["live_planner"] = live_planner
        handoff = {
            "schema_version": "1.0",
            "planning_version": "1.1",
            "phase": 1,
            "status": "planning_complete_not_built",
            "business_summary": positioning["positioning_statement"],
            "primary_customer": customer["primary_launch_segment"],
            "secondary_customers": customer["secondary_segments"],
            "positioning": positioning["positioning_statement"],
            "safe_promise": positioning["safe_customer_promise"],
            "offer_status": offer["product_status_labels"],
            "approved_assumptions": [],
            "pages_or_screens": website["section_order"],
            "page_or_section_contracts": website["section_contracts"],
            "content_rules": {
                "homepage_objective": website["homepage_objective"],
                "placeholder_policy": website["placeholder_policy"],
                "safe_availability_wording": website["safe_availability_wording"],
                "cta_wording_direction": website["cta_wording_direction"],
                "faq_topics": website["faq_topics"],
                "system_must_never_invent": website["system_must_never_invent"],
            },
            "safe_and_forbidden_claims": {
                "safe_message_pillars": positioning["safe_message_pillars"],
                "unsupported_claims_to_avoid": positioning["unsupported_claims_to_avoid"],
            },
            "inquiry_flow": inquiry,
            "local_build_readiness": readiness["local_build_readiness"],
            "public_launch_readiness": readiness["public_launch_readiness"],
            "primary_user_flows": ["Visitor understands the offer", "Visitor reviews trust and FAQ content", "Visitor explores demo-only sample interest behavior without submitting real personal data"],
            "content_requirements": website["section_order"],
            "visual_direction_summary": brand["tone_of_voice"],
            "feature_scope": {
                "must_have": readiness["local_build_readiness"]["allowed_future_phase_2_scope"],
                "later": ["Ordering workflow", "Customer accounts", "Payments", "Delivery integrations", "Analytics"],
                "out_of_scope": ["Payments", "Deployments", "External integrations", "Supplier/customer outreach", "Generated brand assets"],
            },
            "data_entities": ["Product or service", "FAQ item", "Demo inquiry sample"],
            "constraints": constraints,
            "forbidden_actions": forbidden_actions,
            "approval_required_before_phase_2": approvals_needed,
            "phase_2_acceptance_criteria": readiness["local_build_readiness"]["ready_when"],
            "deferred_to_phase_2": [*deferred, "Phase 2 has not started."],
            "policy_boundary_notes": strategic_decisions.get("policy_boundary_notes", []),
        }
        state = {
            "schema_version": "1.0",
            "planning_version": "1.1",
            "phase": 1,
            "phase_status": "planning_complete",
            "build_started": False,
            "build_allowed": False,
            "external_actions_taken": [],
            "external_actions_blocked": blocked_actions,
            "approvals_needed": approvals_needed,
            "local_build_readiness": readiness["local_build_readiness"],
            "public_launch_readiness": readiness["public_launch_readiness"],
            "policy_boundary_notes": strategic_decisions.get("policy_boundary_notes", []),
            "artifact_names": [
                "strategic_decisions.json",
                "business_brief.json",
                "business_brief.md",
                "business_strategy.md",
                "target_customer.md",
                "offer_and_pricing.md",
                "brand_direction.md",
                "website_app_requirements.md",
                "mvp_scope.md",
                "build_handoff.json",
                "planning_qa.md",
                "final_planning_report.md",
                "business_builder_state.json",
            ],
            "deferred_to_phase_2": deferred,
        }
        bundle: dict[str, Any] = {
            "strategic_decisions.json": strategic_decisions,
            "business_brief.json": brief,
            "build_handoff.json": handoff,
            "business_builder_state.json": state,
        }
        bundle["business_brief.md"] = self._business_brief_markdown(brief)
        bundle["business_strategy.md"] = self._business_strategy_markdown(intake, assumptions, strategic_decisions)
        bundle["target_customer.md"] = self._target_customer_markdown(intake, strategic_decisions)
        bundle["offer_and_pricing.md"] = self._offer_pricing_markdown(intake, strategic_decisions)
        bundle["brand_direction.md"] = self._brand_direction_markdown(intake, strategic_decisions)
        bundle["website_app_requirements.md"] = self._website_requirements_markdown(intake, handoff)
        bundle["mvp_scope.md"] = self._mvp_scope_markdown(handoff)
        bundle["final_planning_report.md"] = self._final_planning_report_markdown(intake, brief, handoff)
        return bundle

    def _business_builder_qa(self, bundle: dict[str, Any]) -> str:
        names = bundle["business_builder_state.json"]["artifact_names"]
        decisions = bundle.get("strategic_decisions.json", {})
        customer = decisions.get("customer_wedge", {})
        validation = decisions.get("validation_plan", {})
        offer = decisions.get("offer_pricing", {})
        handoff = bundle.get("build_handoff.json", {})
        inquiry = handoff.get("inquiry_flow", {})
        local = handoff.get("local_build_readiness", {})
        public = handoff.get("public_launch_readiness", {})
        policy_notes = handoff.get("policy_boundary_notes", [])
        primary = str(customer.get("primary_launch_segment", "")).strip()
        secondary = customer.get("secondary_segments", [])
        research = bundle.get("business_brief.json", {}).get("research_status", {})
        primary_is_assumption = "assumption" in primary.lower() or not research.get("used")
        safe_promise = str(decisions.get("positioning", {}).get("safe_customer_promise") or "")
        promise_lower = safe_promise.lower()
        process_promise_terms = ("availability", "manual", "inquiry", "prototype", "process", "details")
        product_outcome_terms = ("yogurt", "breakfast", "snack", "ordinary", "simple", "thick", "product", "experience")
        process_hits = sum(1 for term in process_promise_terms if term in promise_lower)
        product_hits = sum(1 for term in product_outcome_terms if term in promise_lower)
        safe_promise_is_process_heavy = process_hits >= 2 and product_hits == 0
        policy_lines = _business_builder_policy_qa_lines(handoff, offer, policy_notes)
        qa_lines = [
            (
                "WARN" if primary and primary_is_assumption else "PASS" if primary else "BLOCKED",
                "Primary launch segment is a planning assumption pending validation; it is sufficiently narrow for a local prototype, not proven market evidence." if primary and primary_is_assumption else "primary customer is specific enough" if primary else "primary launch segment is missing",
            ),
            ("PASS" if isinstance(secondary, list) else "WARN", "secondary audiences are separate" if isinstance(secondary, list) else "secondary audiences are not clearly separated"),
            (
                "WARN" if safe_promise and safe_promise_is_process_heavy else "PASS" if safe_promise else "WARN",
                "safe promise is partly about prototype/process limits; confirm the product/customer outcome before treating it as a validated value proposition" if safe_promise and safe_promise_is_process_heavy else "value proposition is customer-focused and has a safe promise" if safe_promise else "safe promise is missing",
            ),
            ("PASS" if decisions.get("positioning", {}).get("unsupported_claims_to_avoid") else "BLOCKED", "unsupported claims are explicitly avoided"),
            ("PASS" if offer.get("product_status_labels") else "WARN", "offer status is clear"),
            ("PASS" if len(validation.get("recommended_validation_questions", [])) >= 5 and len(validation.get("positive_signals", [])) >= 3 and len(validation.get("negative_signals", [])) >= 3 else "WARN", "validation plan has questions, signals, and decision rules"),
            ("PASS" if handoff.get("page_or_section_contracts") else "WARN", "website handoff is buildable"),
            ("PASS" if inquiry.get("local_only_behavior") else "WARN", "inquiry behavior is defined"),
            ("PASS" if local and public and local.get("status") != public.get("status") else "WARN", "local build readiness is separate from public launch readiness"),
            ("PASS", "Phase 2 has not started"),
            ("PASS", "external action has not occurred"),
        ]
        return f"""# Planning QA

- PASS: All required Phase 1 artifacts are specified: {", ".join(names)}.
- PASS: Facts from user and assumptions are separated in business_brief.json.
- PASS: Search state is truthful: used={bundle["business_brief.json"]["research_status"]["used"]}, sources={bundle["business_brief.json"]["research_status"]["source_count"]}.
- PASS: Memory state is recorded separately from post-run ingestion.
- PASS: Constraints and forbidden actions are reflected.
- PASS: No Phase 2 build occurred.
- PASS: No external action occurred.
- PASS: Build handoff is present for later controlled implementation.
- WARN: Missing user decisions and approvals must be reviewed before Phase 2.

## Policy QA
{chr(10).join(f"- {status}: {message}." for status, message in policy_lines)}

## Semantic QA
{chr(10).join(f"- {status}: {message}." for status, message in qa_lines)}
"""

    def _split_business_lines(self, value: str) -> list[str]:
        if not value:
            return []
        parts = [item.strip(" -\n\t.") for item in value.replace(";", "\n").split("\n")]
        return [item for item in parts if item]

    def _business_brief_markdown(self, brief: dict[str, Any]) -> str:
        return f"""# Business Brief

Phase: {brief["phase"]}
Status: {brief["status"]}
Planning version: {brief.get("planning_version", "1.0")}

## Strategic Summary
- Primary launch segment: {brief.get("primary_launch_segment", "Not available for this earlier run")}
- Secondary/later segments: {", ".join(brief.get("secondary_segments", [])) or "None listed"}
- Local prototype readiness: {brief.get("local_build_readiness", {}).get("status", "Not available")}
- Public launch readiness: {brief.get("public_launch_readiness", {}).get("status", "Not available")}

## Facts From User
{self._markdown_list(brief["facts_from_user"])}

## Assumptions
{self._markdown_list(brief["assumptions"])}

## Research Status
- Enabled: {brief["research_status"]["enabled"]}
- Used: {brief["research_status"]["used"]}
- Source count: {brief["research_status"]["source_count"]}

## Memory Status
- Retrieved count: {brief["memory_status"]["retrieved_count"]}

## Constraints
{self._markdown_list(brief["constraints"])}

## Forbidden Actions
{self._markdown_list(brief["forbidden_actions"])}

## Approvals Needed
{self._markdown_list(brief["approvals_needed"])}

## Deferred To Phase 2
{self._markdown_list(brief["deferred_to_phase_2"])}
"""

    def _business_strategy_markdown(self, intake: dict[str, str], assumptions: list[str], decision: dict[str, Any] | None = None) -> str:
        decisions = decision or self._mock_business_builder_decisions(intake)
        customer = decisions["customer_wedge"]
        positioning = decisions["positioning"]
        validation = decisions["validation_plan"]
        return f"""# Business Strategy

## Primary Launch Wedge
{customer["primary_launch_segment"]}

## Customer Job
{customer["main_customer_job"]}

## Value proposition
{positioning["positioning_statement"]}

## Safe Promise
{positioning["safe_customer_promise"]}

## Differentiation hypotheses
{self._markdown_list(positioning["differentiation_hypotheses"])}

## What is deliberately not claimed
{self._markdown_list([*positioning["what_the_brand_is_not"], *positioning["unsupported_claims_to_avoid"]])}

## Validation plan
Goal: {validation["validation_goal"]}

Target: {validation["interview_or_feedback_target"]}

### Questions
{self._markdown_list(validation["recommended_validation_questions"])}

### Positive signals
{self._markdown_list(validation["positive_signals"])}

### Negative signals
{self._markdown_list(validation["negative_signals"])}

### Decision rules
{self._markdown_list(validation["decision_rules"])}

### Change if validation is weak
{self._markdown_list(validation["what_to_change_if_validation_is_weak"])}

## Key assumptions and risks
{self._markdown_list(assumptions)}
"""

    def _target_customer_markdown(self, intake: dict[str, str], decision: dict[str, Any] | None = None) -> str:
        decisions = decision or self._mock_business_builder_decisions(intake)
        customer = decisions["customer_wedge"]
        validation = decisions["validation_plan"]
        return f"""# Target Customer

## Primary launch segment
{customer["primary_launch_segment"]}

## Secondary/later segments
{self._markdown_list(customer["secondary_segments"])}

## Why this segment first
{customer["why_primary_segment_first"]}

## Use case
{customer["primary_use_case"]}

## Pain / need
{customer["main_customer_job"]}

## Buying trigger
Clear fit for an everyday routine, with enough approved facts to trust the next step.

## Main objections
{self._markdown_list(customer["main_objections"])}

## Customer validation needed
{self._markdown_list(customer["customer_validation_needed"])}

## Customer journey assumptions
- Discover the business.
- Understand the offer.
- Review trust/FAQ content.
- Use a future manually reviewed inquiry flow.

## Validation questions
{self._markdown_list(validation["recommended_validation_questions"])}
"""

    def _offer_pricing_markdown(self, intake: dict[str, str], decision: dict[str, Any] | None = None) -> str:
        decisions = decision or self._mock_business_builder_decisions(intake)
        offer = decisions["offer_pricing"]
        return f"""# Offer And Pricing

## Anchor offer
{offer["anchor_offer"]}

## Exploratory options
{self._markdown_list(offer["exploratory_variants"])}

## Confirmed / planned / exploratory status
{self._product_status_markdown(offer["product_status_labels"])}

## Customer value hypotheses
{self._markdown_list(offer["customer_value_hypotheses"])}

## Pricing inputs required
{self._markdown_list(offer["pricing_inputs_required"])}

## Pricing validation questions
{self._markdown_list(offer["pricing_validation_questions"])}

## Trial-offer framework
{offer["trial_offer_framework"]}

## Future repeat-purchase framework
{offer["future_repeat_purchase_framework"]}

## Explicit unknowns
{self._markdown_list(offer["explicitly_unknown"])}
"""

    def _brand_direction_markdown(self, intake: dict[str, str], decision: dict[str, Any] | None = None) -> str:
        decisions = decision or self._mock_business_builder_decisions(intake)
        brand = decisions["brand"]
        return f"""# Brand Direction

## Brand principles
{self._markdown_list(brand["brand_principles"])}

## Tone of voice
{brand["tone_of_voice"]}

## Say examples
{self._markdown_list(brand["say_examples"])}

## Avoid examples
{self._markdown_list(brand["avoid_examples"])}

## Visual direction
{self._markdown_list(brand["visual_hierarchy"])}

## Photography/illustration direction
{brand["photography_or_illustration_direction"]}

## Trust cues allowed
{self._markdown_list(brand["trust_cues_allowed"])}

## Trust cues not allowed
{self._markdown_list(brand["trust_cues_not_allowed"])}

## Design anti-patterns
{self._markdown_list(brand["design_anti_patterns"])}
"""

    def _website_requirements_markdown(self, intake: dict[str, str], handoff: dict[str, Any]) -> str:
        local = handoff.get("local_build_readiness", {})
        public = handoff.get("public_launch_readiness", {})
        return f"""# Website App Requirements

## Homepage objective
{handoff.get("content_rules", {}).get("homepage_objective") or intake["primary_goal"] or "Explain the business and prepare a controlled Phase 2 MVP."}

## Primary customer
{handoff.get("primary_customer", "Not available for this earlier run")}

## Secondary customers
{self._markdown_list(handoff.get("secondary_customers", []))}

## Section order
{self._markdown_list(handoff.get("pages_or_screens", []))}

## Page / section contracts
{self._section_contracts_markdown(handoff.get("page_or_section_contracts", []))}

## Primary user flows
{self._markdown_list(handoff["primary_user_flows"])}

## Placeholder policy
{handoff.get("content_rules", {}).get("placeholder_policy", "Use labelled placeholders for unknown facts.")}

## Safe availability wording
{handoff.get("content_rules", {}).get("safe_availability_wording", "Availability must remain explicitly unconfirmed until approved.")}

## CTA wording direction
{handoff.get("content_rules", {}).get("cta_wording_direction", "Use interest/learn language, not order/pay language.")}

## FAQ topics
{self._markdown_list(handoff.get("content_rules", {}).get("faq_topics", []))}

## Local demo inquiry flow
{self._inquiry_flow_markdown(handoff.get("inquiry_flow", {}))}

## Trust and safety requirements
- Claims, pricing, delivery, compliance, and operations need approval or evidence before launch.

## What the system must never invent
{self._markdown_list(handoff.get("content_rules", {}).get("system_must_never_invent", []))}

## Out-of-scope features
{self._markdown_list(handoff["feature_scope"]["out_of_scope"])}

## Approval-required integrations
- Payments, messaging, delivery, analytics, account systems, and any external API.

## Local prototype readiness
- Status: {local.get("status", "unknown")}
- Mode: {local.get("prototype_mode", "local_demo_only")}
- Personal data: {local.get("personal_data", "not_collected")}
- Allowed scope: {", ".join(local.get("allowed_future_phase_2_scope", []))}
- Exclusions: {", ".join(local.get("exclusions", []))}

## Public launch readiness
- Status: {public.get("status", "not_ready")}
- Blockers: {", ".join(public.get("blockers", []))}
"""

    def _mvp_scope_markdown(self, handoff: dict[str, Any]) -> str:
        local = handoff.get("local_build_readiness", {})
        public = handoff.get("public_launch_readiness", {})
        return f"""# MVP Scope

## Local prototype scope
{self._markdown_list(local.get("allowed_future_phase_2_scope", handoff["feature_scope"]["must_have"]))}

## Local prototype readiness
- Status: {local.get("status", "unknown")}
- Ready when:
{self._markdown_list(local.get("ready_when", []))}
- Blockers:
{self._markdown_list(local.get("local_build_blockers", []))}
- Open content assumptions:
{self._markdown_list(local.get("open_content_assumptions", []))}
- Placeholder policy: {local.get("approved_placeholder_policy", "Use labelled placeholders for unresolved facts.")}

## Should have later
{self._markdown_list(handoff["feature_scope"]["later"])}

## Explicit local prototype exclusions
{self._markdown_list(local.get("exclusions", handoff["feature_scope"]["out_of_scope"]))}

## Public-launch scope
Public launch is separate from local prototype creation and remains not ready.

## Public launch readiness
- Status: {public.get("status", "not_ready")}
- Blockers:
{self._markdown_list(public.get("blockers", []))}
- Evidence required:
{self._markdown_list(public.get("evidence_required", []))}
- Operational requirements:
{self._markdown_list(public.get("operational_requirements", []))}
- External approvals required:
{self._markdown_list(public.get("external_action_approvals_required", []))}

## Risks and dependencies
- User must approve assumptions.
- Evidence is needed for claims and pricing.
- Phase 2 must be explicitly requested.

## Acceptance criteria for Phase 2 readiness
{self._markdown_list(handoff["phase_2_acceptance_criteria"])}
"""

    def _final_planning_report_markdown(self, intake: dict[str, str], brief: dict[str, Any], handoff: dict[str, Any]) -> str:
        local = brief.get("local_build_readiness", {})
        public = brief.get("public_launch_readiness", {})
        return f"""# Final Planning Report

This is a Phase 1 planning package.
No website, app, deployment, external integration, social post, ad campaign, payment flow, or external action has been created.

Planning version: {brief.get("planning_version", "1.0")}

## Business concept
{intake["idea"]}

## Primary launch segment
{brief.get("primary_launch_segment", "Not available for this earlier run")}

## Safe promise
{handoff.get("safe_promise", "Not available for this earlier run")}

## Pricing status
No final pricing is set unless supplied and approved by the user. Pricing remains a validation item.

## Brand direction
{handoff["visual_direction_summary"]}

## Website/app MVP requirements
{self._markdown_list(handoff["feature_scope"]["must_have"])}

## Key risks
{self._markdown_list(brief["assumptions"])}

## Approvals needed
{self._markdown_list(brief["approvals_needed"])}

## What is intentionally not built
{self._markdown_list(brief["deferred_to_phase_2"])}

## Local Phase 2 prototype readiness
- Status: {local.get("status", "unknown")}
- Allowed local scope:
{self._markdown_list(local.get("allowed_future_phase_2_scope", []))}
- Blockers:
{self._markdown_list(local.get("local_build_blockers", []))}
- Open content assumptions:
{self._markdown_list(local.get("open_content_assumptions", []))}

## Public launch readiness
- Status: {public.get("status", "not_ready")}
- Blockers:
{self._markdown_list(public.get("blockers", []))}

## What is ready for review
- A structured strategic decision record exists.
- A compact build handoff exists.
- Assumptions and unresolved approvals are visible.
- Local prototype readiness is separated from public launch readiness.
- Phase 2 has not started.
"""

    def _product_status_markdown(self, items: list[dict[str, Any]]) -> str:
        if not items:
            return "- None supplied."
        return "\n".join(f"- {item.get('label', 'Item')}: {item.get('status', 'exploratory')} - {item.get('notes', '')}" for item in items)

    def _section_contracts_markdown(self, contracts: list[dict[str, Any]]) -> str:
        if not contracts:
            return "- Not available for this earlier run."
        blocks = []
        for contract in contracts:
            blocks.append(
                f"### {contract.get('section_name', contract.get('section_id', 'Section'))}\n"
                f"- Section ID: {contract.get('section_id', '')}\n"
                f"- Purpose: {contract.get('purpose', '')}\n"
                f"- Content order:\n{self._markdown_list(contract.get('content_order', []))}\n"
                f"- Required copy topics:\n{self._markdown_list(contract.get('required_copy_topics', []))}\n"
                f"- Safe claims allowed:\n{self._markdown_list(contract.get('safe_claims_allowed', []))}\n"
                f"- Claims/content forbidden:\n{self._markdown_list(contract.get('claims_or_content_forbidden', []))}\n"
                f"- Primary CTA: {contract.get('primary_cta', '')}\n"
                f"- Secondary CTA: {contract.get('secondary_cta', '')}\n"
                f"- If information is unknown: {contract.get('status_if_information_is_unknown', '')}"
            )
        return "\n\n".join(blocks)

    def _inquiry_flow_markdown(self, flow: dict[str, Any]) -> str:
        if not flow:
            return "- Not available for this earlier run."
        return f"""- Purpose: {flow.get("inquiry_purpose", "")}
- Allowed inquiry types: {", ".join(flow.get("allowed_inquiry_types", []))}
- Fields: {", ".join(flow.get("fields", []))}
- Required vs optional: {", ".join(flow.get("required_vs_optional_fields", []))}
- Local-only behavior: {flow.get("local_only_behavior", "")}
- Storage behavior: {flow.get("storage_behavior", "")}
- Success state: {flow.get("success_state", "")}
- Error state: {flow.get("error_state", "")}
- Privacy/data placeholder: {flow.get("privacy_or_data_handling_placeholder", "")}
- Non-goals: {", ".join(flow.get("non_goals", []))}"""

    def _markdown_list(self, items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items) if items else "- None supplied."

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


def _dedupe_list(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        normalized = str(value).strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _clean_list(values: Any, *, limit: int = 10) -> list[str]:
    if not isinstance(values, list):
        return []
    return _dedupe_list([str(value).strip() for value in values if str(value).strip()])[:limit]


def _canonical_business_builder_local_readiness() -> dict[str, Any]:
    return {
        "status": "conditionally_ready",
        "policy_source": "system_deterministic",
        "prototype_mode": "local_demo_only",
        "personal_data": "not_collected",
        "ready_when": [
            "owner accepts placeholder policy",
            "Phase 2 local prototype is explicitly requested",
            "no public claims or integrations are requested",
        ],
        "local_build_blockers": [
            "owner has not accepted placeholder policy",
            "Phase 2 local prototype has not been explicitly requested",
            "a requested feature would introduce public claims or external integration",
        ],
        "open_content_assumptions": [
            "product facts remain pending verification",
            "pricing remains unresolved",
            "availability remains unresolved",
        ],
        "allowed_future_phase_2_scope": [
            "local non-deployed landing page",
            "static content sections",
            "local demo-only inquiry form",
            "sample FAQ",
        ],
        "exclusions": [
            "deployment",
            "payments",
            "real orders",
            "external messaging",
            "analytics",
            "public claims",
        ],
        "approved_placeholder_policy": "Use labelled placeholders and status labels for unresolved product facts, pricing, and availability.",
    }


def _canonical_business_builder_inquiry_flow() -> dict[str, Any]:
    return {
        "mode": "local_demo_only",
        "policy_source": "system_deterministic",
        "inquiry_purpose": "Future local prototype demo input only; not a real inquiry, order, or external message.",
        "allowed_inquiry_types": ["sample interest", "use-case preference", "plain/flavour preference"],
        "fields": ["interest type", "use-case preference", "plain/flavour preference", "optional fictional sample note"],
        "required_vs_optional_fields": ["required demo fields: interest type", "optional demo fields: use-case preference, plain/flavour preference, fictional sample note"],
        "local_only_behavior": "Local demo only. No real personal data. No external submission, email, WhatsApp, CRM, manual-review queue, real order, or payment.",
        "storage_behavior": "If implemented later, store fictional/sample local demo data only. Do not request or store real contact details.",
        "success_state": "Demo saved locally. No order was placed, no real personal data was collected, and no external message was sent.",
        "error_state": "Show local validation errors for missing demo-only fields.",
        "privacy_or_data_handling_placeholder": "Demo-only wording: use fictional/sample values. No real personal data is collected.",
        "non_goals": ["name", "nickname", "city", "area", "address", "email", "phone", "real consent collection", "WhatsApp", "CRM", "payment", "delivery", "analytics", "real order acceptance", "manual-review queue"],
    }


def _canonical_business_builder_cta_wording() -> str:
    return "Use demo/prototype language such as Explore the prototype, Save sample interest (demo), or View availability status. Avoid real commerce or external-contact wording."


def _phase2a_safe_availability_wording(value: Any) -> str:
    default = "Planning-stage local prototype; products, pricing, and public availability are pending approval. The demo form is fictional and does not create a real inquiry, order, payment, contact record, or external message."
    text = str(value or "").strip()
    if not text:
        return default
    lowered = text.lower()
    unsafe_phrases = (
        "register interest",
        "join interest",
        "interest list",
        "manual inquiry",
        "manual inquiries",
        "inquiries will be reviewed",
        "ask a question",
        "contact us",
        "whatsapp",
        "order",
        "payment",
        "delivery",
        "submit",
    )
    if any(phrase in lowered for phrase in unsafe_phrases):
        return default
    return text


def _contains_business_builder_capability(value: str) -> bool:
    lowered = value.lower()
    capability_terms = ("online ordering", "delivery", "subscription", "recurring", "checkout", "payment", "customer account", "messaging", "whatsapp", "email", "crm", "manual review queue")
    return any(term in lowered for term in capability_terms)


def _contains_real_cta(value: str) -> bool:
    lowered = value.lower()
    real_cta_terms = ("sign up", "order now", "place order", "checkout", "pay now", "payment", "delivery", "email us", "whatsapp", "contact us", "submit inquiry")
    return any(term in lowered for term in real_cta_terms)


def _contains_business_builder_personal_data_field(value: str) -> bool:
    personal_terms = ("name", "nickname", "city", "area", "address", "email", "phone", "contact", "consent")
    return any(term in value.lower() for term in personal_terms)


def _contains_real_inquiry_claim(value: str) -> bool:
    lowered = value.lower()
    if "external submission" in lowered and "no external submission" not in lowered:
        return True
    if ("manual review" in lowered or "manual-review" in lowered or "review queue" in lowered) and "no manual-review queue" not in lowered and "no manual review" not in lowered:
        return True
    positive_terms = ("real inquiry", "customer record", "order request", "send email", "send whatsapp", "submit to crm")
    return any(term in lowered for term in positive_terms)


def _contains_local_blocker_misclassification(values: Any) -> bool:
    text = json.dumps(values).lower()
    terms = ("pricing", "product facts", "availability", "compliance", "privacy approval", "public privacy")
    return any(term in text for term in terms)


def _business_builder_policy_qa_lines(handoff: dict[str, Any], offer: dict[str, Any], policy_notes: Any) -> list[tuple[str, str]]:
    local = handoff.get("local_build_readiness", {})
    inquiry = handoff.get("inquiry_flow", {})
    content_rules = handoff.get("content_rules", {})
    product_labels = offer.get("product_status_labels", [])
    product_text = json.dumps(product_labels).lower()
    inquiry_fields_text = json.dumps([*inquiry.get("fields", []), *inquiry.get("required_vs_optional_fields", [])]).lower()
    inquiry_behavior_text = " ".join(
        str(inquiry.get(key, ""))
        for key in ("inquiry_purpose", "local_only_behavior", "storage_behavior", "success_state", "privacy_or_data_handling_placeholder")
    ).lower()
    local_blockers = local.get("local_build_blockers", [])
    cta_text = str(content_rules.get("cta_wording_direction", "")).lower()
    real_cta_terms = ("sign up", "order now", "place order", "checkout", "pay now", "payment", "delivery", "email us", "whatsapp", "contact us", "submit inquiry")
    notes = policy_notes if isinstance(policy_notes, list) else []
    lines: list[tuple[str, str]] = []
    lines.append(("WARN", "system policy narrowed conflicting live planner policy suggestions") if notes else ("PASS", "no planner policy conflict required narrowing"))
    lines.append(("PASS" if local.get("status") == "conditionally_ready" and local.get("policy_source") == "system_deterministic" else "BLOCKED", "local readiness uses deterministic system policy"))
    lines.append(("PASS" if local.get("prototype_mode") == "local_demo_only" and local.get("personal_data") == "not_collected" else "BLOCKED", "local prototype is demo-only and does not collect personal data"))
    lines.append(("BLOCKED" if _contains_business_builder_personal_data_field(inquiry_fields_text) else "PASS", "local-demo inquiry excludes real personal-data fields"))
    lines.append(("BLOCKED" if _contains_real_inquiry_claim(inquiry_behavior_text) else "PASS", "local-demo inquiry excludes real submission/manual-review behavior"))
    lines.append(("BLOCKED" if _contains_business_builder_capability(product_text) else "PASS", "product status labels contain products only"))
    lines.append(("BLOCKED" if _contains_local_blocker_misclassification(local_blockers) else "PASS", "open product facts, pricing, and availability are assumptions, not local-build blockers"))
    lines.append(("PASS" if "local non-deployed landing page" in local.get("allowed_future_phase_2_scope", []) else "BLOCKED", "future local website prototype remains allowed after explicit Phase 2 request"))
    lines.append(("BLOCKED" if any(term in cta_text for term in real_cta_terms) else "PASS", "CTA direction does not imply real signup, ordering, payment, delivery, or external contact"))
    return lines


def _clean_decision_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return {key: _clean_decision_value(item) for key, item in value.items()}
    if isinstance(value, list):
        if any(isinstance(item, dict) for item in value):
            return [_clean_decision_value(item) for item in value if isinstance(item, dict)]
        return _clean_list(value, limit=12)
    return value
