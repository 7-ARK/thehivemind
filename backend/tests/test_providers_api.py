def test_api_index_and_favicon_are_intentional(client):
    index = client.get("/")
    assert index.status_code == 200
    payload = index.json()
    assert payload["name"] == "TheHiveMind API"
    assert payload["docs"] == "/docs"
    assert payload["endpoints"]["runs"] == "/api/runs"

    favicon = client.get("/favicon.ico")
    assert favicon.status_code == 204


def test_provider_status_hides_secrets(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    from app.core.config import get_settings

    get_settings.cache_clear()
    response = client.get("/api/providers/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["providers"]["openai"]["configured"] is True
    assert "sk-secret-value" not in response.text
    assert "openai_api_key" not in response.text


def test_live_mode_blocked_when_not_allowed(client):
    response = client.post(
        "/api/providers/test",
        json={
            "provider": "openai",
            "model": "gpt-5.4-nano",
            "mode": "live",
            "prompt": "Reply with one short sentence saying TheHiveMind provider test worked.",
            "max_output_tokens": 80,
        },
    )
    assert response.status_code == 403
    assert "Live provider calls are disabled" in response.text


def test_missing_api_key_gives_clear_error(client, monkeypatch):
    monkeypatch.setenv("ALLOW_LIVE_CALLS", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    from app.core.config import get_settings

    get_settings.cache_clear()
    response = client.post(
        "/api/providers/test",
        json={
            "provider": "openai",
            "model": "gpt-5.4-nano",
            "mode": "live",
            "prompt": "Reply with one short sentence.",
            "max_output_tokens": 20,
        },
    )
    assert response.status_code == 400
    assert "API key is not configured" in response.text


def test_mock_provider_test_writes_usage_log(client):
    response = client.post(
        "/api/providers/test",
        json={
            "provider": "openai",
            "model": "gpt-5.4-nano",
            "mode": "mock",
            "prompt": "Reply with one short sentence saying TheHiveMind provider test worked.",
            "max_output_tokens": 80,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["provider"] == "mock"
    assert payload["usage_log_id"]
    assert payload["estimated_cost_usd"] >= 0

    summary = client.get("/api/usage/summary")
    assert summary.status_code == 200
    summary_payload = summary.json()
    assert summary_payload["total_input_tokens"] > 0
    assert summary_payload["calls_by_provider"]["mock"] == 1
    assert len(summary_payload["recent_calls"]) == 1


def test_usage_summary_empty_shape(client):
    response = client.get("/api/usage/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_estimated_cost_usd"] == 0
    assert payload["calls_by_provider"] == {}
    assert payload["recent_calls"] == []


def test_existing_mock_run_still_works(client):
    response = client.post("/api/runs", json={"command": "Plan a safe launch", "mode": "mock"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert len(payload["events"]) == 7

    usage = client.get("/api/usage/summary?range=all")
    assert usage.status_code == 200
    usage_payload = usage.json()
    assert usage_payload["total_calls"] == 7
    assert usage_payload["calls_by_provider"]["openai"] >= 1
    assert usage_payload["calls_by_provider"]["gemini"] >= 1

    expensive_runs = client.get("/api/usage/expensive-runs?limit=1")
    assert expensive_runs.status_code == 200
    run_payload = expensive_runs.json()["runs"][0]
    assert run_payload["run_id"] == payload["run_id"]
    assert run_payload["title"] == "Plan a safe launch"
