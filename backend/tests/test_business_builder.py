import json
import asyncio

import pytest
from fastapi import HTTPException

from app.agent_registry.planner_service import AgentPlannerService
from app.agent_registry.defaults import AGENTS
from app.agent_registry.schemas import AgentPlanRequest
from app.core.config import get_settings
from app.orchestration.execution_engine import ExecutionEngine
from app.providers.base_provider import ProviderResponse
from app.projects.project_workspace import ProjectWorkspaceManager


REQUIRED_ARTIFACTS = {
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
}


def _intake() -> dict:
    return {
        "idea": "Create a local Greek yogurt brand in Pakistan focused on thick, simple yogurt for everyday breakfast and snacks.",
        "business_type": "Food product brand",
        "market_location": "Pakistan",
        "target_customer": "Urban families and health-conscious adults who want convenient breakfast and snack options.",
        "primary_goal": "Create a clear business plan and future website MVP handoff.",
        "budget": "Not decided yet.",
        "style_preferences": "Warm, clean, simple, trustworthy, modern but not luxury.",
        "product_or_service_details": "Plain Greek yogurt and simple flavoured options.",
        "required_features": "Future website should explain products, build trust, answer questions, and allow a future manually reviewed order-request flow.",
        "constraints": "No invented market prices or health claims. No medical, dietary, protein, nutritional, food-safety, legal, or compliance claims.",
        "forbidden_actions": "Do not contact suppliers or customers. Do not deploy. Do not build the website in Phase 1.",
    }


def _artifact_content(client, run: dict, name: str) -> str:
    artifact = next(item for item in run["artifacts"] if item["name"] == name)
    return client.get(f"/api/runs/{run['run_id']}/artifacts/{artifact['id']}").json()["content"]


def test_business_builder_mock_success_creates_phase1_artifacts_and_state(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Business Builder Phase 1 planning only.",
            "mode": "mock",
            "run_type": "business_builder",
            "project_id": "business-builder-test",
            "allow_web_search": False,
            "use_memory": False,
            "allow_ceo_live": False,
            "max_cost_usd": 0.05,
            "business_intake": _intake(),
        },
    )
    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "completed"
    assert run["mode"] == "mock"
    assert run["run_type"] == "business_builder"
    assert run["usage_summary"]["selected_workflow"] == "business_builder"
    assert [item["agent_id"] for item in run["agent_plan"]["selected_agents"]] == ["business_planner_agent", "qa_agent"]
    assert any(event["agent_name"] == "Business Planner" for event in run["events"])
    assert any(event["agent_name"] == "Planning QA" for event in run["events"])
    assert not any(event["agent_name"] == "Research Agent" for event in run["events"])
    assert REQUIRED_ARTIFACTS <= {item["name"] for item in run["artifacts"]}
    assert run["commands_run"] == []
    assert not any(event["agent_name"] == "Real Coding Agent" for event in run["events"])
    assert not any(event["agent_name"] == "Website Agent" for event in run["events"])
    assert not any(event["agent_name"] == "Safe Command Runner" for event in run["events"])
    assert not any(path.startswith("website/") for path in run["project_files_created"] + run["project_files_updated"])
    detail = run["usage_summary"]["business_builder"]
    assert detail["phase"] == 1
    assert detail["status"] == "planning_complete"
    assert detail["build_status"] == "Not built"
    assert detail["build_started"] is False
    assert detail["build_allowed"] is False
    assert detail["execution_mode"] == "deterministic_mock_planner"
    assert detail["actual_provider"] == "mock"
    assert detail["actual_model"] == "mock_business_planner"
    assert detail["live_strategic_planner_target"] == "gpt-5.5:flex"
    assert detail["live_call_made"] is False
    assert detail["provider_call_status"] == "not_called_mock"
    assert detail["search_status"] == {"enabled": False, "used": False, "source_count": 0}
    planner = next(item for item in run["agent_plan"]["selected_agents"] if item["agent_id"] == "business_planner_agent")
    assert planner["selected_model"]["selected_model_id"] == "mock_business_planner"
    assert planner["selected_model"]["live_strategic_planner_target"] == "gpt-5.5:flex"
    assert planner["selected_model"]["provider"] == "mock"
    assert "qwen/qwen3-coder" not in json.dumps(planner["selected_model"])
    assert "moonshotai/kimi-k2.7-code" not in json.dumps(planner["selected_model"])
    state = json.loads(ProjectWorkspaceManager().read_project_file("business-builder-test", "business_builder_state.json"))
    assert state["phase"] == 1
    assert state["build_started"] is False
    assert state["build_allowed"] is False
    assert state["external_actions_taken"] == []


def test_business_builder_api_run_merges_stale_agent_registry_and_completes(client):
    settings = get_settings()
    registry_root = settings.project_path.parent / "agent_registry"
    registry_root.mkdir(parents=True, exist_ok=True)
    stale_agents = [agent for agent in AGENTS if agent["id"] != "business_planner_agent"]
    (registry_root / "agents.json").write_text(json.dumps(stale_agents, indent=2), encoding="utf-8")
    response = client.post(
        "/api/runs",
        json={
            "command": "Business Builder Phase 1 planning only.",
            "mode": "mock",
            "run_type": "business_builder",
            "project_id": "business-builder-stale-registry",
            "allow_web_search": False,
            "use_memory": False,
            "business_intake": _intake(),
        },
    )
    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "completed"
    assert [item["agent_id"] for item in run["agent_plan"]["selected_agents"]] == ["business_planner_agent", "qa_agent"]
    assert REQUIRED_ARTIFACTS <= {item["name"] for item in run["artifacts"]}
    assert "business_planner_agent" in {agent["id"] for agent in json.loads((registry_root / "agents.json").read_text(encoding="utf-8"))}


def test_business_builder_rejects_missing_or_blank_idea(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Business Builder Phase 1 planning only.",
            "mode": "mock",
            "run_type": "business_builder",
            "project_id": "blank-business-builder",
            "business_intake": {"idea": "   "},
        },
    )
    assert response.status_code == 422
    assert "business_intake.idea" in response.text


def test_business_builder_search_and_memory_off_do_not_select_research_or_fabricate_sources(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Business Builder Phase 1 planning only. Do not browse. Do not run web search. No web search.",
            "mode": "mock",
            "run_type": "business_builder",
            "project_id": "business-builder-search-off",
            "allow_web_search": False,
            "use_memory": False,
            "business_intake": _intake(),
        },
    )
    assert response.status_code == 200
    run = response.json()
    selected_ids = [item["agent_id"] for item in run["agent_plan"]["selected_agents"]]
    assert selected_ids == ["business_planner_agent", "qa_agent"]
    assert run["usage_summary"]["search_needed"] is False
    assert run["usage_summary"]["search_unavailable"] is False
    assert not any(event["agent_name"] == "Research Agent" for event in run["events"])
    assert run["memory"]["retrieved_snippets"] == []
    brief = json.loads(_artifact_content(client, run, "business_brief.json"))
    assert brief["research_status"] == {"enabled": False, "used": False, "source_count": 0}
    assert brief["memory_status"]["retrieved_count"] == 0
    assert "facts_from_user" in brief
    assert "assumptions" in brief
    assert "deferred_to_phase_2" in brief
    final_report = _artifact_content(client, run, "final_planning_report.md")
    assert "This is a Phase 1 planning package." in final_report
    assert "No website, app, deployment, external integration" in final_report


def test_business_builder_planner_preserves_allowed_research_path(client):
    plan = AgentPlannerService().plan(
        AgentPlanRequest(
            command="Research competitors with web search for a business idea before Phase 1 planning.",
            run_type="business_builder",
            allow_search=True,
        )
    )
    assert [agent.agent_id for agent in plan.selected_agents] == ["business_planner_agent", "research_agent", "qa_agent"]
    assert plan.search_needed is True
    assert plan.search_unavailable is False


def test_business_builder_live_model_policy_targets_registered_gpt55_flex(client):
    plan = AgentPlannerService().plan(
        AgentPlanRequest(
            command="Business Builder Phase 1 planning only.",
            run_type="business_builder",
            mode="live",
            allow_search=False,
        )
    )
    planner = next(agent for agent in plan.selected_agents if agent.agent_id == "business_planner_agent")
    assert planner.selected_model
    assert planner.selected_model["selected_model_id"] == "gpt-5.5:flex"
    assert planner.selected_model["provider_model_name"] == "gpt-5.5"
    assert planner.selected_model["service_tier"] == "flex"
    assert planner.selected_model["provider"] == "openai"
    assert planner.selected_model["selected_model_id"] not in {"qwen/qwen3-coder", "moonshotai/kimi-k2.7-code"}


def test_business_builder_allowed_research_full_run_completes_without_phase2_work(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Research competitors for a business idea before Phase 1 planning.",
            "mode": "mock",
            "run_type": "business_builder",
            "project_id": "business-builder-research-path",
            "allow_web_search": True,
            "use_memory": False,
            "business_intake": _intake(),
        },
    )
    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "completed"
    assert [item["agent_id"] for item in run["agent_plan"]["selected_agents"]] == ["business_planner_agent", "research_agent", "qa_agent"]
    assert any(event["agent_name"] == "Research Agent" for event in run["events"])
    assert not any(event["agent_name"] == "Real Coding Agent" for event in run["events"])
    assert not any(event["agent_name"] == "Website Agent" for event in run["events"])
    assert not any(event["agent_name"] == "Safe Command Runner" for event in run["events"])
    assert not any(path.startswith("website/") for path in run["project_files_created"] + run["project_files_updated"])
    assert REQUIRED_ARTIFACTS <= {item["name"] for item in run["artifacts"]}


def test_business_builder_live_missing_approval_returns_approval_required(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Business Builder Phase 1 planning only.",
            "mode": "live",
            "run_type": "business_builder",
            "project_id": "business-builder-live-approval",
            "allow_ceo_live": True,
            "allow_web_search": False,
            "use_memory": False,
            "business_intake": _intake(),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "approval_required"
    approval_types = {item["approval_type"] for item in payload["approval_requests"]}
    assert {"live_mode", "expensive_ceo_model"} <= approval_types


def test_business_builder_live_gates_block_before_provider_call(monkeypatch, client):
    monkeypatch.setenv("ALLOW_LIVE_CALLS", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    calls = {"count": 0}

    async def fake_generate_with_provider(**kwargs):
        calls["count"] += 1
        raise AssertionError("provider call should be blocked")

    monkeypatch.setattr("app.orchestration.execution_engine.generate_with_provider", fake_generate_with_provider)
    settings = get_settings()
    engine = ExecutionEngine(settings)
    with pytest.raises(HTTPException, match="allow_ceo_live=true"):
        asyncio.run(
            engine.execute_run(
                command="Business Builder Phase 1 planning only.",
                mode="live",
                run_type="business_builder",
                project_id="business-builder-live-gate",
                allow_ceo_live=False,
                allow_web_search=False,
                use_memory=False,
                business_intake=type("Intake", (), _intake())(),
            )
        )
    assert calls["count"] == 0

    with pytest.raises(HTTPException, match="exceeds request max_cost_usd"):
        asyncio.run(
            engine.execute_run(
                command="Business Builder Phase 1 planning only.",
                mode="live",
                run_type="business_builder",
                project_id="business-builder-live-cost",
                allow_ceo_live=True,
                allow_web_search=False,
                use_memory=False,
                max_cost_usd=0.000001,
                business_intake=type("Intake", (), _intake())(),
            )
        )
    assert calls["count"] == 0


def test_business_builder_live_global_flag_gate_before_call(monkeypatch, client):
    calls = {"count": 0}

    async def fake_generate_with_provider(**kwargs):
        calls["count"] += 1
        raise AssertionError("provider call should be blocked")

    monkeypatch.setattr("app.orchestration.execution_engine.generate_with_provider", fake_generate_with_provider)
    monkeypatch.setenv("ALLOW_LIVE_CALLS", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    get_settings.cache_clear()
    with pytest.raises(HTTPException, match="Live provider calls are disabled"):
        asyncio.run(
            ExecutionEngine(get_settings()).execute_run(
                command="Business Builder Phase 1 planning only.",
                mode="live",
                run_type="business_builder",
                project_id="business-builder-live-disabled",
                allow_ceo_live=True,
                allow_web_search=False,
                use_memory=False,
                business_intake=type("Intake", (), _intake())(),
            )
        )
    assert calls["count"] == 0

    assert calls["count"] == 0


def test_business_builder_live_provider_key_gate_before_call(monkeypatch, client):
    monkeypatch.setenv("ALLOW_LIVE_CALLS", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    with pytest.raises(HTTPException, match="openai API key is not configured"):
        asyncio.run(
            ExecutionEngine(get_settings()).execute_run(
                command="Business Builder Phase 1 planning only.",
                mode="live",
                run_type="business_builder",
                project_id="business-builder-provider-missing",
                allow_ceo_live=True,
                allow_web_search=False,
                use_memory=False,
                max_cost_usd=0.25,
                business_intake=type("Intake", (), _intake())(),
            )
        )


def test_business_builder_live_success_uses_one_mocked_gpt55_flex_call(monkeypatch, client):
    monkeypatch.setenv("ALLOW_LIVE_CALLS", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("MAX_COST_PER_RUN_USD", "1.00")
    monkeypatch.setenv("MAX_COST_PER_CALL_USD", "1.00")
    get_settings.cache_clear()
    calls: list[dict] = []

    async def fake_generate_with_provider(**kwargs):
        calls.append(kwargs)
        bundle = ExecutionEngine(get_settings())._business_builder_bundle(
            command="Business Builder Phase 1 planning only.",
            intake=_intake(),
            allow_web_search=False,
            memory_retrieved_count=0,
            research_status={"enabled": False, "used": False, "source_count": 0},
        )
        return (
            ProviderResponse(
                provider="openai",
                model="gpt-5.5",
                text=json.dumps(bundle),
                input_tokens=100,
                output_tokens=200,
                estimated_cost_usd=0.01,
                latency_ms=1,
                raw_metadata={"response_id": "resp-business-builder-test"},
            ),
            "usage-business-builder",
        )

    monkeypatch.setattr("app.orchestration.execution_engine.generate_with_provider", fake_generate_with_provider)
    run = asyncio.run(
        ExecutionEngine(get_settings()).execute_run(
            command="Business Builder Phase 1 planning only.",
            mode="live",
            run_type="business_builder",
            project_id="business-builder-live-success",
            allow_ceo_live=True,
            allow_web_search=False,
            use_memory=False,
            max_cost_usd=1.0,
            business_intake=type("Intake", (), _intake())(),
        )
    )
    assert run.status == "completed"
    assert len(calls) == 1
    assert calls[0]["provider"] == "openai"
    assert calls[0]["model"] == "gpt-5.5"
    assert calls[0]["service_tier"] == "flex"
    assert calls[0]["request_type"] == "business_builder_live_planning"
    assert run.usage_summary["business_builder"]["live_strategic_planner_target"] == "gpt-5.5:flex"
    assert run.usage_summary["business_builder"]["live_call_made"] is True
    assert run.usage_summary["business_builder"]["actual_provider"] == "openai"
    assert run.usage_summary["business_builder"]["actual_model"] == "gpt-5.5"
    assert any(event.agent_name == "Planning QA" and event.model_used != "gpt-5.5" for event in run.events)
    assert not any(event.agent_name in {"Real Coding Agent", "Website Agent", "Safe Command Runner"} for event in run.events)
    assert REQUIRED_ARTIFACTS <= {artifact.name for artifact in run.artifacts}
    assert not any(path.startswith("website/") for path in run.project_files_created + run.project_files_updated)


def test_business_builder_live_malformed_output_fails_without_mock_or_coding_fallback(monkeypatch, client):
    monkeypatch.setenv("ALLOW_LIVE_CALLS", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("MAX_COST_PER_RUN_USD", "1.00")
    monkeypatch.setenv("MAX_COST_PER_CALL_USD", "1.00")
    get_settings.cache_clear()
    calls: list[dict] = []

    async def fake_generate_with_provider(**kwargs):
        calls.append(kwargs)
        return (
            ProviderResponse(
                provider="openai",
                model="gpt-5.5",
                text="{}",
                input_tokens=100,
                output_tokens=5,
                estimated_cost_usd=0.01,
                latency_ms=1,
                raw_metadata={},
            ),
            "usage-business-builder-bad",
        )

    monkeypatch.setattr("app.orchestration.execution_engine.generate_with_provider", fake_generate_with_provider)
    with pytest.raises(HTTPException, match="missing required artifacts"):
        asyncio.run(
            ExecutionEngine(get_settings()).execute_run(
                command="Business Builder Phase 1 planning only.",
                mode="live",
                run_type="business_builder",
                project_id="business-builder-live-malformed",
                allow_ceo_live=True,
                allow_web_search=False,
                use_memory=False,
                max_cost_usd=1.0,
                business_intake=type("Intake", (), _intake())(),
            )
        )
    assert len(calls) == 1
    assert calls[0]["model"] == "gpt-5.5"


def test_existing_run_types_do_not_require_business_intake(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Research only: Greek yogurt competitor positioning. Do not update files.",
            "mode": "mock",
            "run_type": "research_only",
            "project_id": "business-builder-compat",
            "allow_web_search": False,
        },
    )
    assert response.status_code == 200
    assert response.json()["run_type"] == "research_only"
