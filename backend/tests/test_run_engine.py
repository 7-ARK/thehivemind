from app.core.config import get_settings
from app.memory.current_state import get_current_state


COMMAND = "Create a launch plan for a Greek yogurt business in Pakistan, excluding supplier sourcing and physical yogurt production."


def test_run_engine_mock_run_creates_artifacts_events_usage_and_memory(client):
    response = client.post(
        "/api/runs",
        json={
            "command": COMMAND,
            "mode": "mock",
            "project_id": "greek-yogurt-test",
            "run_type": "business_launch_plan",
            "allow_ceo_live": False,
            "max_cost_usd": 0.25,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    run_id = payload["run_id"]

    assert payload["status"] == "completed"
    assert payload["project_id"] == "greek-yogurt-test"
    assert payload["run_type"] == "business_launch_plan"
    assert len(payload["events"]) == 7
    assert len(payload["artifacts"]) == 8
    assert {artifact["name"] for artifact in payload["artifacts"]} == {
        "ceo_plan.md",
        "model_selection.json",
        "research_brief.md",
        "content_calendar.md",
        "operations_checklist.md",
        "qa_review.md",
        "final_report.md",
        "run_summary.json",
    }
    assert all(event["provider"] for event in payload["events"])
    assert all(event["artifact_id"] for event in payload["events"])

    usage = client.get("/api/usage/summary?range=all").json()
    assert usage["total_calls"] == 7
    assert usage["cost_by_agent"]["Operations Agent"] > 0
    assert usage["search_calls"] == 0

    state = get_current_state()
    assert run_id in state
    assert "greek-yogurt-test" in state

    chunks_file = get_settings().vector_path / "chunks.json"
    assert chunks_file.exists()
    assert "Run Engine v1" in chunks_file.read_text(encoding="utf-8")


def test_run_detail_events_and_artifact_endpoints(client):
    run = client.post("/api/runs", json={"command": COMMAND, "mode": "mock"}).json()
    run_id = run["run_id"]

    detail = client.get(f"/api/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["run_id"] == run_id

    events = client.get(f"/api/runs/{run_id}/events")
    assert events.status_code == 200
    assert len(events.json()) == 7

    artifacts = client.get(f"/api/runs/{run_id}/artifacts")
    assert artifacts.status_code == 200
    artifact = artifacts.json()[0]

    content = client.get(f"/api/runs/{run_id}/artifacts/{artifact['id']}")
    assert content.status_code == 200
    content_payload = content.json()
    assert content_payload["id"] == artifact["id"]
    assert content_payload["content"]


def test_live_run_blocked_when_not_allowed(client):
    response = client.post("/api/runs", json={"command": COMMAND, "mode": "live"})
    assert response.status_code == 403
    assert "Live provider calls are disabled" in response.text


def test_live_ceo_model_is_downgraded_without_explicit_ceo_approval(client):
    from app.orchestration.execution_engine import ExecutionEngine

    engine = ExecutionEngine()
    assert engine._safe_ceo_model(mode="live", allow_ceo_live=False) == get_settings().cheap_worker_model
    assert engine._safe_ceo_model(mode="live", allow_ceo_live=True) == get_settings().ceo_model
