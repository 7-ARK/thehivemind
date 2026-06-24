import json
import asyncio
import sqlite3
from pathlib import Path

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
}

PHASE2A_ARTIFACTS = {
    "phase2a_source_handoff.json",
    "phase2a_policy.json",
    "phase2a_build_spec.json",
    "prototype_file_manifest.json",
    "prototype_technical_qa.md",
    "prototype_visual_qa.md",
    "prototype_final_report.md",
    "phase2a_local_prototype_state.json",
}


def _assert_strict_schema_required_matches_properties(schema: dict, path: str = "schema") -> None:
    if schema.get("type") == "object" and schema.get("additionalProperties") is False:
        properties = schema.get("properties", {})
        assert set(schema.get("required", [])) == set(properties), path
    if schema.get("type") == "array":
        _assert_strict_schema_required_matches_properties(schema.get("items", {}), f"{path}[]")
    for key, child in schema.get("properties", {}).items():
        _assert_strict_schema_required_matches_properties(child, f"{path}.{key}")


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


def _live_decision() -> dict:
    return ExecutionEngine(get_settings())._mock_business_builder_decisions(_intake())


def _artifact_content(client, run: dict, name: str) -> str:
    artifact = next(item for item in run["artifacts"] if item["name"] == name)
    return client.get(f"/api/runs/{run['run_id']}/artifacts/{artifact['id']}").json()["content"]


def _phase1_run(client, project_id: str = "business-builder-phase2a") -> dict:
    response = client.post(
        "/api/runs",
        json={
            "command": "Business Builder Phase 1 planning only.",
            "mode": "mock",
            "run_type": "business_builder",
            "project_id": project_id,
            "allow_web_search": False,
            "use_memory": False,
            "business_intake": _intake(),
        },
    )
    assert response.status_code == 200
    return response.json()


def _phase2a_payload(source_id: str, project_id: str = "business-builder-phase2a", **updates) -> dict:
    payload = {
        "command": f"Business Builder Phase 2A local prototype from source run {source_id}",
        "mode": "mock",
        "run_type": "business_builder",
        "project_id": project_id,
        "business_phase": "phase_2a_local_prototype",
        "source_run_id": source_id,
        "confirm_local_prototype": True,
        "allow_file_writes": True,
        "allow_safe_commands": False,
        "allow_web_search": False,
        "allow_ceo_live": False,
        "use_memory": False,
        "use_real_coding_agent": False,
        "allow_live_coding_model_call": False,
        "real_coding_dry_run": False,
        "real_coding_model": None,
        "real_coding_max_files": None,
        "real_coding_max_repair_attempts": 0,
        "max_cost_usd": 0.05,
    }
    payload.update(updates)
    return payload


def _mutate_saved_run(run_id: str, mutate) -> None:
    db_path = get_settings().sqlite_path
    with sqlite3.connect(db_path) as conn:
        payload = json.loads(conn.execute("SELECT payload FROM runs WHERE run_id = ?", (run_id,)).fetchone()[0])
        mutate(payload)
        conn.execute("UPDATE runs SET status = ?, payload = ? WHERE run_id = ?", (payload["status"], json.dumps(payload), run_id))


def _mutate_run_artifact(run: dict, name: str, mutate) -> None:
    artifact = next(item for item in run["artifacts"] if item["name"] == name)
    path = Path(artifact["path"])
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_business_builder_strict_response_schema_requires_every_property():
    response_format = ExecutionEngine(get_settings())._business_builder_decision_response_format()
    schema = response_format["json_schema"]["schema"]
    _assert_strict_schema_required_matches_properties(schema)


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
    assert detail["live_strategic_planner_target"] == "gpt-5.5"
    assert detail["live_call_made"] is False
    assert detail["provider_call_status"] == "not_called_mock"
    assert detail["search_status"] == {"enabled": False, "used": False, "source_count": 0}
    planner = next(item for item in run["agent_plan"]["selected_agents"] if item["agent_id"] == "business_planner_agent")
    assert planner["selected_model"]["selected_model_id"] == "mock_business_planner"
    assert planner["selected_model"]["live_strategic_planner_target"] == "gpt-5.5"
    assert planner["selected_model"]["provider"] == "mock"
    assert "qwen/qwen3-coder" not in json.dumps(planner["selected_model"])
    assert "moonshotai/kimi-k2.7-code" not in json.dumps(planner["selected_model"])
    state = json.loads(ProjectWorkspaceManager().read_project_file("business-builder-test", "business_builder_state.json"))
    assert state["phase"] == 1
    assert state["planning_version"] == "1.1"
    assert state["build_started"] is False
    assert state["build_allowed"] is False
    assert state["external_actions_taken"] == []
    assert state["local_build_readiness"]["status"] == "conditionally_ready"
    assert state["public_launch_readiness"]["status"] == "not_ready"


def test_business_builder_phase11_mock_full_intake_strategic_contract(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Business Builder Phase 1 planning only.",
            "mode": "mock",
            "run_type": "business_builder",
            "project_id": "business-builder-phase11-contract",
            "allow_web_search": False,
            "use_memory": False,
            "business_intake": _intake(),
        },
    )
    assert response.status_code == 200
    run = response.json()
    decisions = json.loads(_artifact_content(client, run, "strategic_decisions.json"))
    handoff = json.loads(_artifact_content(client, run, "build_handoff.json"))
    state = json.loads(_artifact_content(client, run, "business_builder_state.json"))
    qa = _artifact_content(client, run, "planning_qa.md")

    assert decisions["customer_wedge"]["primary_launch_segment"]
    assert decisions["customer_wedge"]["secondary_segments"]
    assert decisions["customer_wedge"]["main_customer_job"]
    assert decisions["positioning"]["safe_customer_promise"]
    assert len(decisions["validation_plan"]["recommended_validation_questions"]) >= 5
    assert len(decisions["validation_plan"]["positive_signals"]) >= 3
    assert len(decisions["validation_plan"]["negative_signals"]) >= 3
    assert decisions["validation_plan"]["decision_rules"]
    assert decisions["offer_pricing"]["anchor_offer"]
    assert any(item["status"] == "exploratory" for item in decisions["offer_pricing"]["product_status_labels"])
    assert decisions["offer_pricing"]["pricing_inputs_required"]
    assert decisions["brand"]["say_examples"]
    assert decisions["brand"]["avoid_examples"]
    assert handoff["page_or_section_contracts"]
    assert handoff["inquiry_flow"]["local_only_behavior"]
    assert state["local_build_readiness"]["status"] in {"conditionally_ready", "ready_for_review"}
    assert state["public_launch_readiness"]["status"] == "not_ready"
    assert state["build_started"] is False
    assert state["build_allowed"] is False
    assert state["external_actions_taken"] == []
    assert not any(event["agent_name"] in {"Real Coding Agent", "Website Agent", "Safe Command Runner"} for event in run["events"])
    assert not any(path.startswith("website/") for path in run["project_files_created"] + run["project_files_updated"])
    assert run["commands_run"] == []
    assert "Semantic QA" in qa
    assert "WARN: Primary launch segment is a planning assumption pending validation" in qa


def test_business_builder_broad_audience_separates_primary_and_secondary(client):
    intake = _intake()
    intake["target_customer"] = "Urban families, working adults, university students, health-conscious adults, office workers, and parents."
    response = client.post(
        "/api/runs",
        json={
            "command": "Business Builder Phase 1 planning only.",
            "mode": "mock",
            "run_type": "business_builder",
            "project_id": "business-builder-broad-audience",
            "allow_web_search": False,
            "use_memory": False,
            "business_intake": intake,
        },
    )
    assert response.status_code == 200
    run = response.json()
    decisions = json.loads(_artifact_content(client, run, "strategic_decisions.json"))
    primary = decisions["customer_wedge"]["primary_launch_segment"].lower()
    assert "working adults" in primary
    assert "urban families, working adults, university students" not in primary
    assert decisions["customer_wedge"]["secondary_segments"]
    qa = _artifact_content(client, run, "planning_qa.md")
    assert "secondary audiences are separate" in qa
    assert "WARN: Primary launch segment is a planning assumption pending validation" in qa


def test_business_builder_semantic_qa_warns_on_process_only_safe_promise():
    engine = ExecutionEngine(get_settings())
    intake = _intake()
    bundle = engine._business_builder_bundle(
        command="Business Builder Phase 1 planning only.",
        intake=intake,
        allow_web_search=False,
        memory_retrieved_count=0,
    )
    bundle["strategic_decisions.json"]["positioning"]["safe_customer_promise"] = (
        "Clear information, honest availability wording, and a manually reviewed future inquiry path."
    )
    qa = engine._business_builder_qa(bundle)
    assert "WARN: safe promise is partly about prototype/process limits" in qa


def test_business_builder_claims_safety_when_search_off(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Business Builder Phase 1 planning only. Do not browse. Do not use web search.",
            "mode": "mock",
            "run_type": "business_builder",
            "project_id": "business-builder-claims-safety",
            "allow_web_search": False,
            "use_memory": False,
            "business_intake": _intake(),
        },
    )
    assert response.status_code == 200
    run = response.json()
    decisions = json.loads(_artifact_content(client, run, "strategic_decisions.json"))
    assert decisions["positioning"]["safe_customer_promise"] == (
        "A thick, simple yogurt option for ordinary breakfast and snack moments, with product details and availability stated only when approved."
    )
    forbidden_text = json.dumps(
        {
            "safe_customer_promise": decisions["positioning"]["safe_customer_promise"],
            "positioning_statement": decisions["positioning"]["positioning_statement"],
            "safe_message_pillars": decisions["positioning"]["safe_message_pillars"],
            "anchor_offer": decisions["offer_pricing"]["anchor_offer"],
            "say_examples": decisions["brand"]["say_examples"],
        }
    ).lower()
    assert "pkr" not in forbidden_text
    assert "rupees" not in forbidden_text
    assert "grams of protein" not in forbidden_text
    assert "certified" not in forbidden_text
    assert "guaranteed delivery" not in forbidden_text
    assert "best in pakistan" not in forbidden_text
    avoid = decisions["positioning"]["unsupported_claims_to_avoid"]
    assert any("nutrition" in item for item in avoid)
    assert any("food-safety" in item for item in avoid)
    assert any("delivery" in item for item in avoid)
    assert decisions["offer_pricing"]["explicitly_unknown"]
    product_labels = [item["label"].lower() for item in decisions["offer_pricing"]["product_status_labels"]]
    assert product_labels == ["plain greek yogurt", "simple flavoured options"]
    assert "delivery" not in json.dumps(decisions["offer_pricing"]["product_status_labels"]).lower()
    assert "subscription" not in json.dumps(decisions["offer_pricing"]["product_status_labels"]).lower()


def test_business_builder_local_build_and_public_launch_readiness_are_separate(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Business Builder Phase 1 planning only.",
            "mode": "mock",
            "run_type": "business_builder",
            "project_id": "business-builder-readiness-split",
            "allow_web_search": False,
            "use_memory": False,
            "business_intake": _intake(),
        },
    )
    assert response.status_code == 200
    run = response.json()
    state = json.loads(_artifact_content(client, run, "business_builder_state.json"))
    local = state["local_build_readiness"]
    public = state["public_launch_readiness"]
    assert local["status"] == "conditionally_ready"
    assert local["policy_source"] == "system_deterministic"
    assert local["prototype_mode"] == "local_demo_only"
    assert local["personal_data"] == "not_collected"
    assert "local non-deployed landing page" in local["allowed_future_phase_2_scope"]
    assert "product facts remain pending verification" in local["open_content_assumptions"]
    assert "pricing remains unresolved" in local["open_content_assumptions"]
    assert "availability remains unresolved" in local["open_content_assumptions"]
    local_blockers = json.dumps(local["local_build_blockers"]).lower()
    assert "pricing" not in local_blockers
    assert "availability" not in local_blockers
    assert "product facts" not in local_blockers
    assert "placeholder policy" in local_blockers
    assert "unresolved product facts, pricing, and availability" in local["approved_placeholder_policy"].lower()
    assert public["status"] == "not_ready"
    assert public["evidence_required"]
    assert state["build_allowed"] is False
    assert "final price" in json.dumps(json.loads(_artifact_content(client, run, "strategic_decisions.json"))["offer_pricing"]["explicitly_unknown"]).lower()


def test_business_builder_website_handoff_is_build_ready_without_building(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Business Builder Phase 1 planning only.",
            "mode": "mock",
            "run_type": "business_builder",
            "project_id": "business-builder-handoff-complete",
            "allow_web_search": False,
            "use_memory": False,
            "business_intake": _intake(),
        },
    )
    assert response.status_code == 200
    run = response.json()
    handoff = json.loads(_artifact_content(client, run, "build_handoff.json"))
    assert len(handoff["page_or_section_contracts"]) >= 5
    hero = handoff["page_or_section_contracts"][0]
    assert {"section_id", "purpose", "required_copy_topics", "safe_claims_allowed", "claims_or_content_forbidden", "primary_cta", "status_if_information_is_unknown"} <= set(hero)
    assert handoff["content_rules"]["placeholder_policy"]
    assert handoff["content_rules"]["safe_availability_wording"]
    assert handoff["content_rules"]["cta_wording_direction"]
    assert "save sample interest (demo)" in handoff["content_rules"]["cta_wording_direction"].lower()
    assert handoff["inquiry_flow"]["local_only_behavior"]
    assert "no external submission" in handoff["inquiry_flow"]["local_only_behavior"].lower()
    inquiry = handoff["inquiry_flow"]
    inquiry_fields_text = json.dumps(inquiry["fields"]).lower()
    inquiry_text = json.dumps(inquiry).lower()
    assert inquiry["mode"] == "local_demo_only"
    assert inquiry["policy_source"] == "system_deterministic"
    assert "sample" in inquiry_text
    assert "real contact details" in inquiry_text
    assert "name" not in inquiry_fields_text
    assert "nickname" not in inquiry_fields_text
    assert "city" not in inquiry_fields_text
    assert "area" not in inquiry_fields_text
    assert "email" not in inquiry_fields_text
    assert "phone" not in inquiry_fields_text
    assert "contact placeholder" not in inquiry_fields_text
    assert inquiry["success_state"] == "Demo saved locally. No order was placed, no real personal data was collected, and no external message was sent."


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


def test_business_builder_live_model_policy_targets_registered_gpt55(client):
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
    assert planner.selected_model["selected_model_id"] == "gpt-5.5"
    assert planner.selected_model["provider_model_name"] == "gpt-5.5"
    assert planner.selected_model["service_tier"] is None
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


@pytest.mark.parametrize(
    "updates, expected",
    [
        ({"source_run_id": None}, "requires source_run_id"),
        ({"confirm_local_prototype": False}, "confirm_local_prototype=true"),
        ({"mode": "live"}, "requires mode=mock"),
        ({"allow_file_writes": False}, "allow_file_writes must be true"),
        ({"allow_safe_commands": True}, "allow_safe_commands must be false"),
        ({"allow_web_search": True}, "allow_web_search must be false"),
        ({"allow_ceo_live": True}, "allow_ceo_live must be false"),
        ({"use_memory": True}, "use_memory must be false"),
        ({"use_real_coding_agent": True}, "use_real_coding_agent must be false"),
        ({"allow_live_coding_model_call": True}, "allow_live_coding_model_call must be false"),
    ],
)
def test_business_builder_phase2a_rejects_invalid_request_controls(client, updates, expected):
    source = _phase1_run(client, "business-builder-phase2a-rejects")
    response = client.post("/api/runs", json=_phase2a_payload(source["run_id"], "business-builder-phase2a-rejects", **updates))
    assert response.status_code == 422
    assert expected in response.text


def test_business_builder_phase2a_rejects_invalid_source_runs(client):
    source = _phase1_run(client, "business-builder-phase2a-source")

    wrong_project = client.post("/api/runs", json=_phase2a_payload(source["run_id"], "business-builder-other-project"))
    assert wrong_project.status_code == 422
    assert "same project_id" in wrong_project.text

    _mutate_saved_run(source["run_id"], lambda payload: payload.update({"status": "failed"}))
    not_completed = client.post("/api/runs", json=_phase2a_payload(source["run_id"], "business-builder-phase2a-source"))
    assert not_completed.status_code == 422
    assert "must be completed" in not_completed.text

    source = _phase1_run(client, "business-builder-phase2a-incompatible")
    _mutate_saved_run(source["run_id"], lambda payload: payload["usage_summary"]["business_builder"].update({"planning_version": "1.0"}))
    incompatible = client.post("/api/runs", json=_phase2a_payload(source["run_id"], "business-builder-phase2a-incompatible"))
    assert incompatible.status_code == 422
    assert "Phase 1.1 compatible" in incompatible.text


def test_business_builder_phase2a_success_creates_local_prototype_and_artifacts(client):
    source = _phase1_run(client, "business-builder-phase2a-success")
    source_artifact_hashes = {
        name: Path(next(item for item in source["artifacts"] if item["name"] == name)["path"]).read_bytes()
        for name in ["strategic_decisions.json", "build_handoff.json", "business_builder_state.json"]
    }
    response = client.post("/api/runs", json=_phase2a_payload(source["run_id"], "business-builder-phase2a-success"))
    assert response.status_code == 200
    run = response.json()

    assert run["status"] == "completed"
    assert run["usage_summary"]["selected_workflow"] == "business_builder_phase2a_local_prototype"
    assert run["usage_summary"]["business_builder"]["phase"] == "2a"
    assert run["usage_summary"]["business_builder"]["source_run_id"] == source["run_id"]
    assert PHASE2A_ARTIFACTS <= {item["name"] for item in run["artifacts"]}
    assert run["metrics"]["total_estimated_cost_usd"] == 0
    assert run["usage_summary"]["business_builder"]["external_calls"] == 0
    assert run["commands_run"] == []
    assert not any(event["agent_name"] in {"Real Coding Agent", "Website Agent", "Safe Command Runner"} for event in run["events"])
    assert {event["provider"] for event in run["events"]} == {"deterministic_local"}
    assert {event["model_used"] for event in run["events"]} == {"none"}
    assert sorted(run["project_files_created"]) == sorted(
        [
            f"prototypes/{run['run_id']}/README.md",
            f"prototypes/{run['run_id']}/index.html",
            f"prototypes/{run['run_id']}/prototype_manifest.json",
        ]
    )
    manager = ProjectWorkspaceManager()
    assert manager.resolve("business-builder-phase2a-success", f"prototypes/{run['run_id']}/index.html").is_file()
    assert manager.resolve("business-builder-phase2a-success", f"prototypes/{run['run_id']}/README.md").is_file()
    assert manager.resolve("business-builder-phase2a-success", f"prototypes/{run['run_id']}/prototype_manifest.json").is_file()
    manifest = json.loads(_artifact_content(client, run, "prototype_file_manifest.json"))
    assert manifest["preview_route"] == f"/api/projects/business-builder-phase2a-success/prototypes/{run['run_id']}/preview"
    assert len(manifest["generated_files"]) == 3
    technical_qa = _artifact_content(client, run, "prototype_technical_qa.md")
    assert "BLOCKED:" not in technical_qa
    state = json.loads(_artifact_content(client, run, "phase2a_local_prototype_state.json"))
    assert state == {
        "phase": "2a",
        "status": "local_prototype_completed",
        "source_run_id": source["run_id"],
        "prototype_mode": "local_demo_only",
        "prototype_created": True,
        "public_launch_allowed": False,
        "external_actions_taken": [],
        "personal_data_collected": False,
        "provider_calls": 0,
    }
    for name, before in source_artifact_hashes.items():
        assert Path(next(item for item in source["artifacts"] if item["name"] == name)["path"]).read_bytes() == before


def test_business_builder_phase2a_prototype_policy_and_preview(client):
    source = _phase1_run(client, "business-builder-phase2a-policy")
    response = client.post("/api/runs", json=_phase2a_payload(source["run_id"], "business-builder-phase2a-policy"))
    assert response.status_code == 200
    run = response.json()
    html_text = ProjectWorkspaceManager().read_project_file("business-builder-phase2a-policy", f"prototypes/{run['run_id']}/index.html")
    for section_id in ["header", "hero", "product-concept", "everyday-use", "starter-range", "trust-transparency", "availability-status", "faq", "sample-interest", "footer-disclaimer"]:
        assert f'id="{section_id}"' in html_text
    for text in [
        "This is a local prototype.",
        "Public availability is not confirmed.",
        "No online orders are accepted.",
        "No payments are accepted.",
        "No real personal data is collected.",
        "No external message is sent.",
        "Demo saved locally. No order was placed, no real personal data was collected, and no external message was sent.",
        "Save sample interest (demo)",
    ]:
        assert text in html_text
    lowered = html_text.lower()
    for forbidden in ["http://", "https://", "fetch(", "xmlhttprequest", "websocket", "localstorage", "sessionstorage", "mailto:", "tel:", 'type="email"', 'type="tel"', 'name="name"', 'name="city"', 'name="address"', "buy now", "order now", "checkout", "whatsapp", "register interest"]:
        assert forbidden not in lowered
    preview = client.get(f"/api/projects/business-builder-phase2a-policy/prototypes/{run['run_id']}/preview")
    assert preview.status_code == 200
    assert "text/html" in preview.headers["content-type"]
    assert "Local demo-only sample-interest form" in preview.text
    assert client.get("/api/projects/business-builder-phase2a-policy/prototypes/missing-run/preview").status_code == 404
    assert client.get("/api/projects/business-builder-phase2a-policy/prototypes/..%5C..%5Csecret/preview").status_code == 404


def test_business_builder_phase2a_filters_operational_capabilities_from_product_statuses():
    engine = ExecutionEngine(get_settings())
    decisions = _live_decision()
    decisions["offer_pricing"]["product_status_labels"] = [
        {"label": "Plain Greek yogurt", "status": "planned", "notes": "Product concept."},
        {"label": "Online ordering", "status": "planned", "notes": "Should not render."},
        {"label": "Delivery", "status": "planned", "notes": "Should not render."},
        {"label": "Subscription checkout payment", "status": "planned", "notes": "Should not render."},
    ]
    spec = engine._phase2a_build_spec(decisions, {"page_or_section_contracts": []}, engine._phase2a_policy())
    labels = [item["label"].lower() for item in spec["approved_product_statuses"]]
    assert labels == ["plain greek yogurt"]
    assert "delivery" not in json.dumps(spec["approved_product_statuses"]).lower()
    assert "checkout" not in json.dumps(spec["approved_product_statuses"]).lower()
    assert "payment" not in json.dumps(spec["approved_product_statuses"]).lower()


def test_business_builder_phase2a_filters_unsafe_source_availability_wording():
    engine = ExecutionEngine(get_settings())
    decisions = _live_decision()
    decisions["website_spec"]["safe_availability_wording"] = (
        "Public availability is not yet confirmed. You can register interest or ask a question, "
        "and inquiries will be reviewed manually as the product plan develops."
    )
    policy = engine._phase2a_policy()
    spec = engine._phase2a_build_spec(decisions, {"page_or_section_contracts": []}, policy)
    html_text = engine._render_phase2a_index_html(spec, policy).lower()
    assert "register interest" not in html_text
    assert "ask a question" not in html_text
    assert "inquiries will be reviewed" not in html_text
    assert "save sample interest (demo)" in html_text


def test_business_builder_phase2a_normalizes_source_sentence_punctuation_through_api(client):
    source = _phase1_run(client, "business-builder-phase2a-punctuation")
    _mutate_run_artifact(
        source,
        "strategic_decisions.json",
        lambda payload: (
            payload["customer_wedge"].update(
                {
                    "primary_launch_segment": "people who want a simple everyday yogurt option.",
                    "primary_use_case": "home meals..",
                }
            ),
            payload["positioning"].update({"safe_customer_promise": "A simple yogurt concept for breakfast..."}),
            payload["offer_pricing"]["product_status_labels"][0].update({"notes": "Suitable for ordinary home meals.."}),
        ),
    )
    response = client.post("/api/runs", json=_phase2a_payload(source["run_id"], "business-builder-phase2a-punctuation"))
    assert response.status_code == 200
    run = response.json()
    html_text = ProjectWorkspaceManager().read_project_file("business-builder-phase2a-punctuation", f"prototypes/{run['run_id']}/index.html")
    assert "option.. The first use case is" not in html_text
    assert "home meals.." not in html_text
    assert "breakfast..." not in html_text
    assert "option. The first use case is home meals." in html_text
    assert "A simple yogurt concept for breakfast." in html_text
    assert "Suitable for ordinary home meals." in html_text


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
    monkeypatch.setenv("MAX_COST_PER_RUN_USD", "1.00")
    monkeypatch.setenv("MAX_COST_PER_CALL_USD", "1.00")
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
                max_cost_usd=1.0,
                business_intake=type("Intake", (), _intake())(),
            )
        )


def test_business_builder_live_success_uses_one_mocked_gpt55_call(monkeypatch, client):
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
                text=json.dumps(_live_decision()),
                input_tokens=100,
                output_tokens=300,
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
    assert calls[0]["service_tier"] is None
    assert calls[0]["max_output_tokens"] == get_settings().business_builder_live_max_output_tokens
    assert calls[0]["request_type"] == "business_builder_live_planning"
    assert calls[0]["response_format"]["type"] == "json_schema"
    assert calls[0]["response_format"]["json_schema"]["name"] == "business_builder_phase1_decisions"
    assert run.usage_summary["business_builder"]["live_strategic_planner_target"] == "gpt-5.5"
    assert run.usage_summary["business_builder"]["live_call_made"] is True
    assert run.usage_summary["business_builder"]["actual_provider"] == "openai"
    assert run.usage_summary["business_builder"]["actual_model"] == "gpt-5.5"
    assert any(event.agent_name == "Planning QA" and event.model_used != "gpt-5.5" for event in run.events)
    assert "compact strategy decisions" in run.events[0].output_summary
    assert not any(event.agent_name in {"Real Coding Agent", "Website Agent", "Safe Command Runner"} for event in run.events)
    assert REQUIRED_ARTIFACTS <= {artifact.name for artifact in run.artifacts}
    assert not any(path.startswith("website/") for path in run.project_files_created + run.project_files_updated)
    brief = next(artifact for artifact in run.artifacts if artifact.name == "business_brief.json")
    brief_content = json.loads(Path(brief.path).read_text(encoding="utf-8"))
    assert brief_content["live_planner"]["used"] is True
    assert brief_content["live_planner"]["output_mode"] == "strategic_decisions_v1_1"
    assert brief_content["primary_launch_segment"]
    assert brief_content["public_launch_readiness"]["status"] == "not_ready"


def test_business_builder_live_normalizes_public_launch_status_variant(monkeypatch, client):
    monkeypatch.setenv("ALLOW_LIVE_CALLS", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("MAX_COST_PER_RUN_USD", "1.00")
    monkeypatch.setenv("MAX_COST_PER_CALL_USD", "1.00")
    get_settings.cache_clear()

    async def fake_generate_with_provider(**kwargs):
        decision = _live_decision()
        decision["readiness"]["public_launch_readiness"]["status"] = "not ready"
        return (
            ProviderResponse(
                provider="openai",
                model="gpt-5.5",
                text=json.dumps(decision),
                input_tokens=100,
                output_tokens=300,
                estimated_cost_usd=0.01,
                latency_ms=1,
                raw_metadata={"response_id": "resp-business-builder-status-normalized"},
            ),
            "usage-business-builder-status-normalized",
        )

    monkeypatch.setattr("app.orchestration.execution_engine.generate_with_provider", fake_generate_with_provider)
    run = asyncio.run(
        ExecutionEngine(get_settings()).execute_run(
            command="Business Builder Phase 1 planning only.",
            mode="live",
            run_type="business_builder",
            project_id="business-builder-live-status-normalized",
            allow_ceo_live=True,
            allow_web_search=False,
            use_memory=False,
            max_cost_usd=1.0,
            business_intake=type("Intake", (), _intake())(),
        )
    )
    assert run.status == "completed"
    brief = next(artifact for artifact in run.artifacts if artifact.name == "business_brief.json")
    brief_content = json.loads(Path(brief.path).read_text(encoding="utf-8"))
    assert brief_content["public_launch_readiness"]["status"] == "not_ready"


def test_business_builder_live_conflicting_policy_is_narrowed_to_demo_only(monkeypatch, client):
    monkeypatch.setenv("ALLOW_LIVE_CALLS", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("MAX_COST_PER_RUN_USD", "1.00")
    monkeypatch.setenv("MAX_COST_PER_CALL_USD", "1.00")
    get_settings.cache_clear()

    async def fake_generate_with_provider(**kwargs):
        decision = _live_decision()
        decision["offer_pricing"]["product_status_labels"].append(
            {"label": "Online ordering and delivery", "status": "planned", "notes": "Customers can order for delivery."}
        )
        decision["inquiry_flow"] = {
            "inquiry_purpose": "Collect real customer inquiries for manual review.",
            "allowed_inquiry_types": ["order request", "delivery request"],
            "fields": ["name", "city", "email", "phone", "consent checkbox"],
            "required_vs_optional_fields": ["required: name, email, phone, consent"],
            "local_only_behavior": "Submit inquiry for manual review.",
            "storage_behavior": "Record customer details locally for follow-up.",
            "success_state": "Inquiry submitted for manual review.",
            "error_state": "Show validation errors.",
            "privacy_or_data_handling_placeholder": "Privacy approval pending.",
            "non_goals": ["payments"],
        }
        decision["readiness"]["local_build_readiness"] = {
            "status": "blocked",
            "ready_when": ["public privacy approval is complete"],
            "blockers": ["pricing unresolved", "product facts unresolved", "availability unresolved", "public privacy approval missing"],
            "allowed_scope": ["local non-deployed landing page", "local inquiry form"],
            "exclusions": ["website build", "deployment", "payments"],
            "approved_placeholder_policy": "Needs approval.",
        }
        decision["website_spec"]["cta_wording_direction"] = "Sign up for delivery and submit inquiry."
        decision["website_spec"]["section_contracts"][0]["primary_cta"] = "Order now"
        return (
            ProviderResponse(
                provider="openai",
                model="gpt-5.5",
                text=json.dumps(decision),
                input_tokens=100,
                output_tokens=300,
                estimated_cost_usd=0.01,
                latency_ms=1,
                raw_metadata={"response_id": "resp-business-builder-policy-conflict"},
            ),
            "usage-business-builder-policy-conflict",
        )

    monkeypatch.setattr("app.orchestration.execution_engine.generate_with_provider", fake_generate_with_provider)
    run = asyncio.run(
        ExecutionEngine(get_settings()).execute_run(
            command="Business Builder Phase 1 planning only.",
            mode="live",
            run_type="business_builder",
            project_id="business-builder-live-policy-conflict",
            allow_ceo_live=True,
            allow_web_search=False,
            use_memory=False,
            max_cost_usd=1.0,
            business_intake=type("Intake", (), _intake())(),
        )
    )
    assert run.status == "completed"
    handoff = json.loads(Path(next(artifact for artifact in run.artifacts if artifact.name == "build_handoff.json").path).read_text(encoding="utf-8"))
    state = json.loads(Path(next(artifact for artifact in run.artifacts if artifact.name == "business_builder_state.json").path).read_text(encoding="utf-8"))
    qa = Path(next(artifact for artifact in run.artifacts if artifact.name == "planning_qa.md").path).read_text(encoding="utf-8")

    product_text = json.dumps(handoff["offer_status"]).lower()
    assert "online ordering" not in product_text
    assert "delivery" not in product_text
    inquiry = handoff["inquiry_flow"]
    inquiry_fields = json.dumps(inquiry["fields"]).lower()
    assert inquiry["mode"] == "local_demo_only"
    assert inquiry["policy_source"] == "system_deterministic"
    assert "name" not in inquiry_fields
    assert "city" not in inquiry_fields
    assert "email" not in inquiry_fields
    assert "phone" not in inquiry_fields
    assert inquiry["success_state"] == "Demo saved locally. No order was placed, no real personal data was collected, and no external message was sent."
    local = state["local_build_readiness"]
    assert local["status"] == "conditionally_ready"
    assert local["policy_source"] == "system_deterministic"
    assert "local non-deployed landing page" in local["allowed_future_phase_2_scope"]
    assert "website build" not in json.dumps(local["exclusions"]).lower()
    assert "pricing" not in json.dumps(local["local_build_blockers"]).lower()
    assert "pricing remains unresolved" in local["open_content_assumptions"]
    assert handoff["public_launch_readiness"]["status"] == "not_ready"
    assert "System policy narrowed the local prototype handoff to demo-only behavior." in handoff["policy_boundary_notes"]
    assert "WARN: system policy narrowed conflicting live planner policy suggestions" in qa
    assert "PASS: product status labels contain products only" in qa


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
    with pytest.raises(HTTPException, match="missing object"):
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
