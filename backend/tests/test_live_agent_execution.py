import json

from app.agents.llm_agent_runner import AgentOutput
from app.storage.usage_store import UsageStore


PROTOTYPE_COMMAND = "Create a simple Greek yogurt order website prototype with files."


async def fake_live_runner(context, system_prompt, user_prompt, *, settings=None, usage_store=None, request_type="agent_execution"):
    store = usage_store or UsageStore(settings)
    usage_id = store.log_call(
        run_id=context.run_id,
        task_id=f"{context.run_id}:{request_type}",
        agent_name=context.agent_name,
        agent_role=context.agent_role,
        provider=context.provider,
        model=context.model,
        mode=context.mode,
        request_type=request_type,
        input_tokens=32,
        output_tokens=24,
        estimated_cost_usd=0.0001,
        latency_ms=3,
        success=True,
        metadata={"project_id": context.project_id, "simulated_live": True},
    )
    if request_type == "file_generation":
        text = json.dumps(
            {
                "file_actions": [
                    {
                        "operation": "create",
                        "path": "website/live_agent_note.md",
                        "summary": "Live-simulated file action output.",
                        "content": "# Live Agent Note\n\nThis file was produced by a simulated live file action.\n",
                    }
                ]
            }
        )
    else:
        text = f"# {context.agent_name}\n\nSimulated live output for {context.task_objective}."
    return AgentOutput(
        agent_name=context.agent_name,
        model=context.model,
        provider=context.provider,
        output_text=text,
        structured_summary=text[:120],
        usage_log_id=usage_id,
        estimated_cost_usd=0.0001,
        input_tokens=32,
        output_tokens=24,
        latency_ms=3,
    )


def enable_live(monkeypatch):
    monkeypatch.setenv("ALLOW_LIVE_CALLS", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    from app.core.config import get_settings

    get_settings.cache_clear()


def approve_required(client, payload):
    initial = client.post("/api/runs", json=payload)
    assert initial.status_code == 200
    approval_payload = initial.json()
    assert approval_payload["status"] == "approval_required"

    approval_ids = []
    for approval in approval_payload["approval_requests"]:
        decision = client.post(
            f"/api/approvals/{approval['id']}/decision",
            json={"decision": "approved", "reason": "test approval"},
        )
        assert decision.status_code == 200
        approval_ids.append(approval["id"])

    return {**payload, "approval_ids": approval_ids}


def test_run_live_mode_blocked_when_not_allowed(client):
    payload = {
        "command": PROTOTYPE_COMMAND,
        "mode": "live",
        "project_id": "greek-yogurt-live",
        "run_type": "prototype_build",
        "allow_file_writes": True,
        "allow_safe_commands": True,
    }
    approved_payload = approve_required(client, payload)
    response = client.post("/api/runs", json=approved_payload)
    assert response.status_code == 403
    assert "Live provider calls are disabled" in response.text


def test_live_run_uses_fallback_ceo_model_when_ceo_live_not_allowed(client, monkeypatch):
    enable_live(monkeypatch)
    monkeypatch.setattr("app.orchestration.execution_engine.run_llm_agent", fake_live_runner)

    payload = {
        "command": PROTOTYPE_COMMAND,
        "mode": "live",
        "project_id": "greek-yogurt-live",
        "run_type": "prototype_build",
        "allow_file_writes": True,
        "allow_safe_commands": True,
        "allow_ceo_live": False,
        "max_cost_usd": 0.25,
    }
    approved_payload = approve_required(client, payload)
    response = client.post("/api/runs", json=approved_payload)
    assert response.status_code == 200
    payload = response.json()
    ceo_event = next(event for event in payload["events"] if event["agent_name"] == "CEO Agent")
    assert ceo_event["model_used"] == "gpt-5.4-nano"
    assert "gpt-5.5" not in payload["models_used"]
    assert "website/live_agent_note.md" in payload["project_files_created"]

    usage = client.get("/api/usage/summary?range=all").json()
    assert usage["total_calls"] >= 6
    assert usage["calls_by_provider"]["openai"] >= 1


def test_live_run_can_use_ceo_model_only_when_explicitly_allowed(client, monkeypatch):
    enable_live(monkeypatch)
    monkeypatch.setattr("app.orchestration.execution_engine.run_llm_agent", fake_live_runner)

    payload = {
        "command": PROTOTYPE_COMMAND,
        "mode": "live",
        "project_id": "greek-yogurt-ceo-live",
        "run_type": "prototype_build",
        "allow_file_writes": True,
        "allow_safe_commands": False,
        "allow_ceo_live": True,
        "max_cost_usd": 0.25,
    }
    approved_payload = approve_required(client, payload)
    response = client.post("/api/runs", json=approved_payload)
    assert response.status_code == 200
    payload = response.json()
    ceo_event = next(event for event in payload["events"] if event["agent_name"] == "CEO Agent")
    assert ceo_event["model_used"] == "gpt-5.5"


async def invalid_file_json_runner(context, system_prompt, user_prompt, *, settings=None, usage_store=None, request_type="agent_execution"):
    output = await fake_live_runner(context, system_prompt, user_prompt, settings=settings, usage_store=usage_store, request_type=request_type)
    if request_type == "file_generation":
        output.output_text = "not valid json"
    return output


def test_invalid_live_file_action_json_falls_back_without_crashing(client, monkeypatch):
    enable_live(monkeypatch)
    monkeypatch.setattr("app.orchestration.execution_engine.run_llm_agent", invalid_file_json_runner)

    payload = {
        "command": PROTOTYPE_COMMAND,
        "mode": "live",
        "project_id": "greek-yogurt-invalid-json",
        "run_type": "prototype_build",
        "allow_file_writes": True,
        "allow_safe_commands": True,
        "allow_ceo_live": False,
        "max_cost_usd": 0.25,
    }
    approved_payload = approve_required(client, payload)
    response = client.post("/api/runs", json=approved_payload)
    assert response.status_code == 200
    payload = response.json()
    assert "website/app.py" in payload["project_files_created"]
    file_event = next(event for event in payload["events"] if event["agent_name"] == "File Builder Agent")
    assert "invalid JSON" in file_event["output_summary"]


def test_live_budget_limit_blocks_run_safely(client, monkeypatch):
    enable_live(monkeypatch)
    monkeypatch.setattr("app.orchestration.execution_engine.run_llm_agent", fake_live_runner)

    payload = {
        "command": PROTOTYPE_COMMAND,
        "mode": "live",
        "project_id": "greek-yogurt-budget",
        "run_type": "prototype_build",
        "allow_file_writes": True,
        "allow_safe_commands": True,
        "allow_ceo_live": False,
        "max_cost_usd": 0.0001,
    }
    approved_payload = approve_required(client, payload)
    response = client.post("/api/runs", json=approved_payload)
    assert response.status_code == 400
    assert "exceeds request max_cost_usd" in response.text
