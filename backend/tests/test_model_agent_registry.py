import pytest

from app.agent_registry.planner_service import AgentPlannerService
from app.agent_registry.schemas import AgentPlanRequest
from app.model_registry.registry_loader import ModelRegistryLoader
from app.model_registry.schemas import ModelSelectionRequest
from app.model_registry.selector_service import DynamicModelSelector
from app.workspace.command_runner import SafeCommandRunner


def test_model_registry_loads(client):
    models = ModelRegistryLoader().models()
    assert {model.id for model in models} >= {"gpt-5.5", "gpt-5.4-nano", "gemini-3.5-flash", "qwen/qwen3-coder", "moonshotai/kimi-k2.7-code"}
    assert all(model.best_for is not None for model in models)


def test_model_registry_merges_new_defaults_without_overwriting_local_overrides(client):
    from app.core.config import get_settings

    settings = get_settings()
    loader = ModelRegistryLoader(settings)
    legacy_models = [
        {
            **model.model_dump(),
            "enabled": False if model.id == "gpt-5.4-nano" else model.enabled,
        }
        for model in loader.models()
        if model.id != "moonshotai/kimi-k2.7-code"
    ]
    (loader.store.root / "models.json").write_text(__import__("json").dumps(legacy_models), encoding="utf-8")

    reloaded = ModelRegistryLoader(settings).models()
    by_id = {model.id: model for model in reloaded}
    assert "moonshotai/kimi-k2.7-code" in by_id
    assert by_id["gpt-5.4-nano"].enabled is False


def test_disabled_models_are_not_selectable(client, tmp_path, monkeypatch):
    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    loader = ModelRegistryLoader(settings)
    models = [model.model_dump() for model in loader.models()]
    for model in models:
        if model["id"] == "gpt-5.4-nano":
            model["enabled"] = False
    loader.store.root.mkdir(parents=True, exist_ok=True)
    (loader.store.root / "models.json").write_text(__import__("json").dumps(models), encoding="utf-8")

    result = DynamicModelSelector(settings).select(
        ModelSelectionRequest(
            command="Use cheap worker models only.",
            agent_id="qa_agent",
            agent_task="Review output.",
            preferred_tags=["qa", "cheap"],
            max_cost_usd=0.05,
        )
    )
    assert result.selected_model_id != "gpt-5.4-nano"


def test_missing_api_key_makes_provider_unavailable(client):
    response = client.get("/api/model-registry/availability?mode=live")
    assert response.status_code == 200
    payload = response.json()
    openai = [item for item in payload["availability"] if item["provider"] == "openai"]
    assert openai
    assert all(item["available"] is False for item in openai)
    assert any("API key" in " ".join(item["reasons"]) for item in openai)


def test_gpt55_filtered_when_user_says_do_not_use_it(client):
    result = DynamicModelSelector().select(
        ModelSelectionRequest(
            command="Website update. Do not use GPT-5.5. Use cheap worker models.",
            agent_id="website_agent",
            agent_task="Update website files.",
            required_capabilities=["coding", "json"],
            preferred_tags=["coding", "cheap"],
            max_cost_usd=0.05,
        )
    )
    assert not result.selected_model_id.startswith("gpt-5.5")
    assert any(item.model_id.startswith("gpt-5.5") for item in result.why_not_others)


def test_cheap_only_filters_high_cost_models(client):
    result = DynamicModelSelector().select(
        ModelSelectionRequest(
            command="Use cheap models only for QA.",
            agent_id="qa_agent",
            agent_task="Review output.",
            preferred_tags=["qa", "cheap"],
            max_cost_usd=0.05,
        )
    )
    assert result.selected_model_id in {"gpt-5.4-nano", "gemini-3.1-flash-lite", "qwen/qwen3-coder"}


def test_search_required_does_not_select_non_search_model_when_search_disabled(client):
    with pytest.raises(ValueError, match="No valid model"):
        DynamicModelSelector().select(
            ModelSelectionRequest(
                command="Research competitors with web search.",
                agent_id="research_agent",
                agent_task="Research competitors.",
                required_capabilities=["search"],
                preferred_tags=["research"],
                search_enabled=False,
                max_cost_usd=0.05,
            )
        )


def test_planner_reports_search_unavailable_instead_of_pretending(client):
    plan = AgentPlannerService().plan(
        AgentPlanRequest(command="Research competitors and latest market trends.", run_type="business_launch_plan", allow_search=False)
    )
    assert plan.search_unavailable is True
    assert any("search is disabled" in note.lower() for note in plan.notes)


def test_website_update_selects_website_and_qa_not_full_launch(client):
    plan = AgentPlannerService().plan(
        AgentPlanRequest(command="Website Agent only: improve homepage copy. Do not deploy.", run_type="website_update", allow_file_writes=True, allow_safe_commands=True)
    )
    ids = [agent.agent_id for agent in plan.selected_agents]
    assert ids == ["website_agent", "qa_agent", "safe_command_runner"]
    assert "operations_agent" in {agent.agent_id for agent in plan.skipped_agents}
    assert "deploy" in plan.blocked_actions
    assert plan.approval_required is False


def test_research_only_selects_research_and_qa(client):
    plan = AgentPlannerService().plan(AgentPlanRequest(command="Research competitors.", allow_search=False))
    assert [agent.agent_id for agent in plan.selected_agents] == ["research_agent", "qa_agent"]


def test_provider_test_selects_provider_test_only(client):
    plan = AgentPlannerService().plan(AgentPlanRequest(command="Run provider test.", run_type="provider_test"))
    assert [agent.agent_id for agent in plan.selected_agents] == ["provider_test_agent"]


def test_negative_deploy_and_install_constraints_do_not_create_approval(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Website Agent only: improve homepage. Do not deploy. Do not install packages.",
            "mode": "mock",
            "run_type": "website_update",
            "project_id": "greek-yogurt-test",
            "allow_file_writes": True,
            "allow_safe_commands": True,
            "max_cost_usd": 0.25,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["agent_plan"]["approval_required"] is False
    assert "deploy" in payload["agent_plan"]["blocked_actions"]
    assert "package_install" in payload["agent_plan"]["blocked_actions"]


def test_prompt_says_do_not_create_files_disables_file_writes_even_if_toggle_on(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Website update only. Do not create files.",
            "mode": "mock",
            "run_type": "website_update",
            "project_id": "greek-yogurt-test",
            "allow_file_writes": True,
            "allow_safe_commands": True,
        },
    )
    assert response.status_code == 403
    assert "file writes" in response.text.lower()


def test_safe_command_runner_uses_project_cwd_and_logs_executable(client):
    from app.projects.project_workspace import ProjectWorkspaceManager

    manager = ProjectWorkspaceManager()
    manager.write_project_file("cmd-test", "website/app.py", "print('ok')\n", "Test", "run-cmd", "app")
    result = SafeCommandRunner().run_project_command("cmd-test", "run-cmd", ["python", "-m", "py_compile", "website/app.py"])
    assert result.exit_code == 0
    assert result.cwd == "."
    assert result.resolved_cwd
    assert result.executable_command


def test_safe_command_runner_logs_stderr_and_reason_on_failure(client):
    from app.projects.project_workspace import ProjectWorkspaceManager

    manager = ProjectWorkspaceManager()
    manager.write_project_file("cmd-fail", "website/bad.py", "def broken(:\n", "Test", "run-fail", "bad")
    result = SafeCommandRunner().run_project_command("cmd-fail", "run-fail", ["python", "-m", "py_compile", "website/bad.py"])
    assert result.exit_code != 0
    assert result.stderr
    assert result.error_type == "validation_error"
    assert result.error_message


def test_run_details_include_selected_model_reason(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Website Agent only: improve homepage copy. Do not use GPT-5.5. Use cheap worker models only.",
            "mode": "mock",
            "run_type": "website_update",
            "project_id": "greek-yogurt-test",
            "allow_file_writes": True,
            "allow_safe_commands": True,
        },
    )
    run = response.json()
    detail = client.get(f"/api/runs/{run['run_id']}/model-selection").json()
    website = detail["model_selection"]["website_agent"]
    assert website["selected_model_id"]
    assert website["reason"]


def test_agent_plan_endpoint_returns_selected_and_skipped_agents(client):
    response = client.post("/api/agent-registry/plan", json={"command": "Website Agent only: improve homepage copy.", "run_type": "website_update", "allow_file_writes": True})
    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_agents"]
    assert payload["skipped_agents"]


def test_model_selection_endpoint_returns_structured_choice(client):
    response = client.post(
        "/api/model-registry/select",
        json={
            "command": "Use cheap worker models.",
            "agent_id": "qa_agent",
            "agent_task": "Review output.",
            "preferred_tags": ["qa", "cheap"],
            "max_cost_usd": 0.05,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_model_id"]
    assert payload["cost_guard"]["within_budget"] is True


def test_registry_endpoints_do_not_leak_secrets(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    response = client.get("/api/model-registry/summary")
    assert response.status_code == 200
    assert "sk-secret-value" not in response.text
    agents = client.get("/api/agent-registry/agents")
    assert "sk-secret-value" not in agents.text


def test_search_provider_registry_has_only_supported_providers(client):
    response = client.get("/api/search-tools/providers")
    assert response.status_code == 200
    provider_ids = {provider["id"] for provider in response.json()["providers"]}
    assert provider_ids == {"exa_direct", "openai_web_search", "gemini_google_search"}
    assert all(provider["provider"] != "openrouter" for provider in response.json()["providers"])


def test_search_status_separates_mock_and_live_availability(client):
    response = client.get("/api/search-tools/status")
    assert response.status_code == 200
    exa = next(provider for provider in response.json()["providers"] if provider["id"] == "exa_direct")
    assert exa["configured"] is False
    assert exa["available"] is False
    assert exa["available_for_live"] is False
    assert exa["live_search_available"] is False
    assert exa["available_in_mock"] is True
    assert exa["mock_fixture_available"] is True
    assert any("EXA_API_KEY" in reason for reason in exa["reasons"])
    assert any("ALLOW_WEB_SEARCH=false" in reason for reason in exa["reasons"])


def test_search_status_allow_web_search_false_blocks_live_even_with_key(client, monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "exa-search-secret")
    monkeypatch.setenv("ENABLE_EXA_SEARCH", "true")
    monkeypatch.setenv("ALLOW_WEB_SEARCH", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()
    response = client.get("/api/search-tools/status")
    exa = next(provider for provider in response.json()["providers"] if provider["id"] == "exa_direct")
    assert exa["configured"] is True
    assert exa["available_for_live"] is True
    assert exa["live_search_available"] is False
    assert exa["mock_fixture_available"] is True


def test_search_selection_reports_disabled_without_pretending(client):
    response = client.post(
        "/api/search-tools/test",
        json={"query": "Research latest competitors", "mode": "mock", "allow_web_search": False},
    )
    assert response.status_code == 200
    selection = response.json()["selection"]
    assert selection["search_needed"] is True
    assert selection["search_unavailable"] is True
    assert "disabled" in selection["reason"].lower()


def test_research_only_run_skips_website_agent(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Research only: latest Greek yogurt competitors. Do not update files.",
            "mode": "mock",
            "run_type": "website_update",
            "project_id": "greek-yogurt-test",
            "allow_file_writes": True,
            "allow_safe_commands": True,
            "allow_web_search": False,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["run_type"] == "research_only"
    assert "Website Agent" not in {event["agent_name"] for event in payload["events"]}
    assert payload["project_files_created"] == []
    assert payload["project_files_updated"] == []


def test_research_run_type_maps_to_research_only_and_has_model(client):
    plan = AgentPlannerService().plan(
        AgentPlanRequest(command="Research latest Greek yogurt competitors.", run_type="research", allow_search=False)
    )
    ids = [agent.agent_id for agent in plan.selected_agents]
    assert plan.selected_workflow == "research_only"
    assert ids == ["research_agent", "qa_agent"]
    research = next(agent for agent in plan.selected_agents if agent.agent_id == "research_agent")
    assert research.selected_model
    assert "error" not in research.selected_model
    assert research.required_search_tool_capabilities == ["web_search"]
    assert "search" not in research.required_model_capabilities
    assert plan.selected_search_provider is None
    assert plan.search_unavailable is True


def test_prompt_research_only_overrides_file_write_toggle(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Research only: latest Greek yogurt competitors. Do not update files.",
            "mode": "mock",
            "run_type": "business_launch_plan",
            "project_id": "greek-yogurt-test",
            "allow_file_writes": True,
            "allow_safe_commands": True,
            "allow_web_search": False,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["run_type"] == "research_only"
    assert payload["project_files_created"] == []
    assert payload["project_files_updated"] == []
    assert "CEO Agent" not in {event["agent_name"] for event in payload["events"]}


def test_mock_research_search_writes_log_and_structured_sources(client, monkeypatch):
    monkeypatch.setenv("ALLOW_WEB_SEARCH", "true")
    monkeypatch.setenv("ENABLE_EXA_SEARCH", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    response = client.post(
        "/api/runs",
        json={
            "command": "Research only: latest Greek yogurt competitors.",
            "mode": "mock",
            "run_type": "research_only",
            "project_id": "greek-yogurt-test",
            "allow_web_search": True,
            "allow_file_writes": False,
            "allow_safe_commands": False,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    logs = client.get("/api/search-tools/logs/recent").json()["logs"]
    assert logs
    assert logs[0]["provider_id"] == "exa_direct"
    assert logs[0]["status"] == "mock_fixture"
    artifacts = client.get(f"/api/runs/{payload['run_id']}/artifacts").json()
    sources_artifact = next(artifact for artifact in artifacts if artifact["name"] == "research_sources.json")
    content = client.get(f"/api/runs/{payload['run_id']}/artifacts/{sources_artifact['id']}").json()["content"]
    import json

    sources_payload = json.loads(content)
    assert sources_payload["search_used"] is True
    assert sources_payload["mock_fixture"] is True
    assert sources_payload["provider_id"] == "exa_direct"
    assert sources_payload["source_count"] > 0


def test_openrouter_discovery_sync_is_metadata_only_and_mocked(client, monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {
                        "id": "vendor/model-a",
                        "name": "Model A",
                        "context_length": 1000,
                        "pricing": {"prompt": "0.1", "completion": "0.2"},
                        "architecture": {"modality": "text->text"},
                    }
                ]
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.model_registry.openrouter_discovery.httpx.AsyncClient", FakeAsyncClient)
    response = client.post("/api/model-registry/discovery/openrouter/sync")
    assert response.status_code == 200
    summary = client.get("/api/model-registry/discovery/openrouter/summary").json()
    assert summary["cached_models_count"] == 1
    assert summary["promoted_to_curated_registry"] is False
