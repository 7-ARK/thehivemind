from app.core.config import get_settings
from app.storage.usage_store import UsageStore


def insert_usage(
    *,
    provider="openai",
    model="gpt-5.4-nano",
    agent_name="Coding Agent",
    agent_role="technical_worker",
    run_id="run-1",
    estimated_cost_usd=0.001,
    success=True,
    input_tokens=1000,
    output_tokens=200,
    cached_tokens=100,
    latency_ms=500,
):
    return UsageStore().log_call(
        run_id=run_id,
        task_id="task-1",
        agent_name=agent_name,
        agent_role=agent_role,
        provider=provider,
        model=model,
        mode="mock",
        request_type="unit_test",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        estimated_cost_usd=estimated_cost_usd,
        latency_ms=latency_ms,
        success=success,
        metadata={"safe": True, "prompt": "must not be exported"},
    )


def test_usage_summary_empty_database_shape(client):
    response = client.get("/api/usage/summary?range=30d")
    assert response.status_code == 200
    payload = response.json()
    assert payload["range"] == "30d"
    assert payload["total_calls"] == 0
    assert payload["effective_cost_usd"] == 0
    assert payload["budget_status"]["status"] == "safe"


def test_usage_breakdowns_with_inserted_logs(client):
    insert_usage(provider="openai", model="gpt-5.4-nano", agent_name="Coding Agent", estimated_cost_usd=0.001)
    insert_usage(provider="gemini", model="gemini-3.1-flash-lite", agent_name="Research Agent", estimated_cost_usd=0.002)

    providers = client.get("/api/usage/providers?range=all").json()["providers"]
    models = client.get("/api/usage/models?range=all").json()["models"]
    agents = client.get("/api/usage/agents?range=all").json()["agents"]

    assert {item["provider"] for item in providers} == {"openai", "gemini"}
    assert models[0]["cost_usd"] >= models[-1]["cost_usd"]
    assert {item["agent_name"] for item in agents} == {"Coding Agent", "Research Agent"}


def test_tokens_latency_failures_recent_and_timeseries(client):
    insert_usage(success=True, latency_ms=100)
    insert_usage(provider="gemini", model="gemini-3.5-flash", success=False, latency_ms=900)

    assert client.get("/api/usage/tokens?range=all").json()["models"]
    assert client.get("/api/usage/latency?range=all").json()["p95_latency_ms"] >= 100
    failures = client.get("/api/usage/failures?range=all").json()
    assert failures["failed_calls"] == 1
    recent = client.get("/api/usage/recent?limit=2").json()["recent_calls"]
    assert len(recent) == 2
    points = client.get("/api/usage/timeseries?range=all&bucket=day").json()["points"]
    assert len(points) == 1
    assert points[0]["calls"] == 2


def test_budget_status_safe_warning_danger(client, monkeypatch):
    monkeypatch.setenv("MONTHLY_AI_BUDGET_USD", "0.001")
    monkeypatch.setenv("WARNING_BUDGET_PERCENT", "70")
    monkeypatch.setenv("DANGER_BUDGET_PERCENT", "90")
    get_settings.cache_clear()

    insert_usage(estimated_cost_usd=0.0005)
    assert client.get("/api/usage/budget?range=all").json()["status"] == "safe"

    insert_usage(estimated_cost_usd=0.0003)
    assert client.get("/api/usage/budget?range=all").json()["status"] == "warning"

    insert_usage(estimated_cost_usd=0.0002)
    assert client.get("/api/usage/budget?range=all").json()["status"] == "exceeded"


def test_cache_and_search_endpoints(client):
    insert_usage(cached_tokens=250)
    cache = client.get("/api/usage/cache?range=all").json()
    search = client.get("/api/usage/search?range=all").json()
    assert cache["cached_tokens"] == 250
    assert cache["estimated_savings_usd"] >= 0
    assert search["total_search_calls"] == 0
    assert "disabled" in search["status"]


def test_expensive_runs_endpoint(client):
    insert_usage(run_id="run-cheap", estimated_cost_usd=0.001)
    insert_usage(run_id="run-expensive", estimated_cost_usd=0.005, input_tokens=2000)
    runs = client.get("/api/usage/expensive-runs?limit=1").json()["runs"]
    assert runs[0]["run_id"] == "run-expensive"
    assert runs[0]["call_count"] == 1


def test_csv_export_safe_columns(client):
    insert_usage()
    response = client.get("/api/usage/export.csv?range=all")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    body = response.text
    assert "created_at,run_id,agent_name,provider,model,mode" in body
    assert "must not be exported" not in body
    assert "prompt" not in body
    assert "sk-" not in body


def test_seed_demo_only_works_in_development(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    blocked = client.post("/api/usage/seed-demo")
    assert blocked.status_code == 403

    monkeypatch.setenv("APP_ENV", "development")
    get_settings.cache_clear()
    seeded = client.post("/api/usage/seed-demo")
    assert seeded.status_code == 200
    assert seeded.json()["inserted"] >= 5
    assert client.get("/api/usage/summary?range=all").json()["total_calls"] >= 5
