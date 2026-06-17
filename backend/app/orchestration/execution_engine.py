import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app.agents.business_agent import BusinessAgent
from app.agents.ceo_agent import CEOAgent
from app.agents.model_selector_agent import ModelSelectorAgent
from app.agents.operations_agent import OperationsAgent
from app.agents.qa_agent import QAAgent
from app.artifacts.artifact_store import ArtifactStore
from app.core.config import Settings, get_settings
from app.core.cost_estimator import assert_run_budget, estimate_cost_usd, estimate_tokens
from app.core.model_registry import get_model_metadata
from app.core.models import AgentInfo, FinalOutput, RunEvent, RunMetrics, RunRecord
from app.memory.current_state import update_current_state
from app.memory.retrieval import retrieve_memory
from app.memory.vector_memory import LocalVectorMemory
from app.orchestration.task_graph import build_default_task_graph
from app.providers.provider_router import generate_with_provider
from app.storage.usage_store import UsageStore


RunResult = RunRecord


async def execute_run(
    command: str,
    mode: str = "mock",
    project_id: str | None = None,
    run_type: str = "business_launch_plan",
    allow_ceo_live: bool = False,
    max_cost_usd: float | None = None,
) -> RunResult:
    return await ExecutionEngine().execute_run(
        command=command,
        mode=mode,
        project_id=project_id,
        run_type=run_type,
        allow_ceo_live=allow_ceo_live,
        max_cost_usd=max_cost_usd,
    )


class ExecutionEngine:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.db_path = self.settings.sqlite_path
        self.artifacts = ArtifactStore(self.settings)
        self.usage = UsageStore(self.settings)
        self._ensure_database()

    async def execute_run(
        self,
        *,
        command: str,
        mode: str = "mock",
        project_id: str | None = None,
        run_type: str = "business_launch_plan",
        allow_ceo_live: bool = False,
        max_cost_usd: float | None = None,
    ) -> RunRecord:
        if mode not in {"mock", "live"}:
            raise HTTPException(status_code=400, detail="mode must be 'mock' or 'live'.")
        if mode == "live":
            self.settings.require_live_allowed()
        else:
            mode = "mock"

        run_id = str(uuid.uuid4())
        started_at = datetime.now(UTC)
        max_cost = min(max_cost_usd or self.settings.max_cost_per_run_usd, self.settings.max_cost_per_run_usd)
        memory = retrieve_memory(command)
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
        self._save_run(record)
        self._update_memory(record, model_selection)
        return record

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
            return self.settings.cheap_worker_model
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
        if mode == "mock":
            input_tokens = estimate_tokens(prompt)
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
            return {
                "run_id": run_id,
                "agent_name": agent_name,
                "agent_role": agent_role,
                "provider": metadata.provider,
                "model": model,
                "request_type": request_type,
                "input": prompt,
                "text": mock_output,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost": cost,
                "latency_ms": 1,
            }

        response, _ = await generate_with_provider(
            provider=metadata.provider,
            model=model,
            mode="live",
            messages=[
                {"role": "system", "content": "You are an agent inside TheHiveMind. Produce concise, structured, safe output. Do not browse the web."},
                {"role": "user", "content": prompt},
            ],
            max_output_tokens=500,
            temperature=0.2,
            service_tier=self.settings.ceo_service_tier if model == self.settings.ceo_model else None,
            run_id=run_id,
            agent_name=agent_name,
            request_type=request_type,
            settings=self.settings,
            usage_store=self.usage,
        )
        return {
            "run_id": run_id,
            "agent_name": agent_name,
            "agent_role": agent_role,
            "provider": metadata.provider,
            "model": model,
            "request_type": request_type,
            "input": prompt,
            "text": response.text,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "cost": response.estimated_cost_usd,
            "latency_ms": response.latency_ms,
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
