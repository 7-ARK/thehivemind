import sys
import types

import httpx
import pytest

from app.providers.base_provider import ProviderResponse
from app.storage.usage_store import UsageStore
from app.orchestration.execution_engine import ExecutionEngine
from app.usage_sync.google_billing_sync import list_google_billing_tables
from app.usage_sync.openai_usage_sync import sync_openai_usage
from app.usage_sync.reconciliation_service import reconcile_provider_usage
from app.usage_sync.sync_store import SyncStore


def test_official_usage_status_handles_missing_keys_and_does_not_leak_secrets(client):
    response = client.get("/api/official-usage/status")
    assert response.status_code == 200
    payload = response.json()

    assert payload["openai"]["admin_key_configured"] is False
    assert payload["openrouter"]["management_key_configured"] is False
    assert payload["google"]["credentials_configured"] is False
    assert "key-openrouter" not in response.text
    assert "sk-" not in response.text


def test_official_usage_status_does_not_return_configured_secret_values(client, monkeypatch):
    monkeypatch.setenv("ENABLE_OPENAI_OFFICIAL_USAGE_SYNC", "true")
    monkeypatch.setenv("OPENAI_ADMIN_API_KEY", "sk-admin-secret")
    monkeypatch.setenv("ENABLE_OPENROUTER_OFFICIAL_USAGE_SYNC", "true")
    monkeypatch.setenv("OPENROUTER_MANAGEMENT_KEY", "key-openrouter-secret")
    from app.core.config import get_settings

    get_settings.cache_clear()
    response = client.get("/api/official-usage/status")
    assert response.status_code == 200
    payload = response.json()

    assert payload["openai"]["admin_key_configured"] is True
    assert payload["openrouter"]["management_key_configured"] is True
    assert "sk-admin-secret" not in response.text
    assert "key-openrouter-secret" not in response.text


@pytest.mark.anyio
async def test_openai_sync_handles_unauthorized_without_crashing(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_OPENAI_OFFICIAL_USAGE_SYNC", "true")
    monkeypatch.setenv("OPENAI_ADMIN_API_KEY", "sk-admin-secret")
    monkeypatch.setenv("PROVIDER_USAGE_STORE_PATH", str(tmp_path / "provider_usage"))
    from app.core.config import get_settings

    get_settings.cache_clear()

    async def fake_get_json(*args, **kwargs):
        request = httpx.Request("GET", "https://api.openai.com/v1/organization/costs")
        response = httpx.Response(401, request=request)
        raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    monkeypatch.setattr("app.usage_sync.openai_usage_sync._get_json", fake_get_json)
    records = await sync_openai_usage()

    assert records == []
    assert SyncStore(get_settings()).status()["openai"]["status"] == "unauthorized"


def test_openrouter_sync_missing_management_key(client, monkeypatch):
    monkeypatch.setenv("ENABLE_OPENROUTER_OFFICIAL_USAGE_SYNC", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    response = client.post("/api/official-usage/sync")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"]["openrouter"]["status"] == "unavailable"
    assert "management key missing" in payload["status"]["openrouter"]["message"]


def test_real_usage_endpoints_exclude_mock_estimates_by_default(client):
    response = client.post(
        "/api/runs",
        json={
            "command": "Create a launch plan for a Greek yogurt business.",
            "mode": "mock",
            "run_type": "business_launch_plan",
            "max_cost_usd": 0.25,
        },
    )
    assert response.status_code == 200

    summary = client.get("/api/usage/real/summary")
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["run_level_provider_cost_usd"] == 0
    assert payload["run_level_tokens"] == 0
    assert payload["dev_estimates_hidden"] is True


def test_openrouter_account_credits_not_counted_as_run_cost(client):
    from app.core.config import get_settings

    settings = get_settings()
    SyncStore(settings).create_record(
        provider="openrouter",
        source="provider_account_balance",
        scope="account",
        provider_reported_cost_usd=3.25,
        raw_usage_metadata={"total_usage": 3.25},
    )

    summary = client.get("/api/usage/real/summary").json()
    billing = client.get("/api/usage/official/account-billing").json()
    assert summary["run_level_provider_cost_usd"] == 0
    assert summary["official_billing_cost_usd"] == 0
    assert summary["account_balance_records"] == 1
    assert "account-level" in billing["records"][0]["note"].lower()


def test_openrouter_account_credits_use_latest_snapshot_not_summed(client):
    from app.core.config import get_settings

    settings = get_settings()
    store = SyncStore(settings)
    store.create_record(
        provider="openrouter",
        source="provider_account_balance",
        scope="account",
        provider_reported_cost_usd=3.36352,
        created_at="2026-06-17T10:00:00+00:00",
        local_created_at="2026-06-17T10:00:00+00:00",
        service="credits",
    )
    store.create_record(
        provider="openrouter",
        source="provider_account_balance",
        scope="account",
        provider_reported_cost_usd=0.168176,
        created_at="2026-06-18T10:00:00+00:00",
        local_created_at="2026-06-18T10:00:00+00:00",
        service="credits",
    )

    summary = client.get("/api/usage/real/summary").json()
    billing = client.get("/api/usage/official/account-billing").json()
    openrouter_cards = [record for record in billing["records"] if record["provider"] == "openrouter"]

    assert summary["official_billing_cost_usd"] == 0
    assert summary["account_balance_records"] == 1
    assert len(openrouter_cards) == 1
    assert openrouter_cards[0]["provider_reported_cost_usd"] == 0.168176


def test_openai_official_rows_are_aggregated_for_account_billing(client):
    from app.core.config import get_settings

    settings = get_settings()
    store = SyncStore(settings)
    store.create_record(
        provider="openai",
        source="provider_official_billing",
        scope="account_or_project",
        provider_reported_cost_usd=0.1,
        created_at="2026-06-17T10:00:00+00:00",
        local_created_at="2026-06-17T10:00:00+00:00",
    )
    store.create_record(
        provider="openai",
        source="provider_official_billing",
        scope="account_or_project",
        provider_reported_cost_usd=None,
        input_tokens=100,
        output_tokens=50,
        created_at="2026-06-17T11:00:00+00:00",
        local_created_at="2026-06-17T11:00:00+00:00",
    )
    store.create_record(
        provider="openai",
        source="provider_official_billing",
        scope="account_or_project",
        provider_reported_cost_usd=0.2,
        created_at="2026-06-18T10:00:00+00:00",
        local_created_at="2026-06-18T10:00:00+00:00",
    )

    summary = client.get("/api/usage/real/summary").json()
    billing = client.get("/api/usage/official/account-billing").json()
    openai_cards = [record for record in billing["records"] if record["provider"] == "openai"]

    assert summary["official_billing_cost_usd"] == 0.3
    assert len(openai_cards) == 1
    assert openai_cards[0]["provider_reported_cost_usd"] == 0.3


def test_openrouter_breakdown_uses_generation_lookup_run_level_data(client):
    from app.core.config import get_settings

    SyncStore(get_settings()).create_record(
        provider="openrouter",
        source="provider_generation_lookup",
        scope="run",
        run_id="run-openrouter-1",
        agent_name="Provider Test Agent",
        requested_model="qwen/qwen3-coder",
        actual_model="qwen/qwen3-coder",
        openrouter_provider_name="Nvidia",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        provider_reported_cost_usd=0.001,
        generation_id="gen-123",
    )

    payload = client.get("/api/usage/real/openrouter-breakdown").json()
    assert any(model["provider_name"] == "Nvidia" for model in payload["models"])
    assert any(record["source"] == "provider_generation_lookup" for record in payload["records"])


@pytest.mark.anyio
async def test_google_billing_sync_handles_missing_tables(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_GOOGLE_BILLING_SYNC", "true")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "reader.json"))
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_ID", "thehivemind-billing")
    monkeypatch.setenv("GOOGLE_BILLING_BIGQUERY_DATASET", "billing_export")
    monkeypatch.setenv("PROVIDER_USAGE_STORE_PATH", str(tmp_path / "provider_usage"))
    from app.core.config import get_settings

    get_settings.cache_clear()

    class FakeDatasetReference:
        def __init__(self, project, dataset):
            self.project = project
            self.dataset = dataset

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def list_tables(self, dataset_ref):
            return []

    fake_google = types.ModuleType("google")
    fake_cloud = types.ModuleType("google.cloud")
    fake_bigquery = types.ModuleType("google.cloud.bigquery")
    fake_bigquery.Client = FakeClient
    fake_bigquery.DatasetReference = FakeDatasetReference
    fake_cloud.bigquery = fake_bigquery
    fake_google.cloud = fake_cloud
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.cloud", fake_cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", fake_bigquery)
    tables = await list_google_billing_tables(get_settings())

    assert tables == []
    assert SyncStore(get_settings()).status()["google"]["status"] == "waiting_for_tables"


@pytest.mark.anyio
async def test_reconciliation_returns_mock_only_when_no_live_usage(client):
    response = client.get("/api/official-usage/reconciliation")
    assert response.status_code == 200
    statuses = {item["provider"]: item["status"] for item in response.json()}
    assert statuses["openai"] == "mock_only"


@pytest.mark.anyio
async def test_reconciliation_returns_estimated_for_live_local_without_official(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("PROVIDER_USAGE_STORE_PATH", str(tmp_path / "provider_usage"))
    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    UsageStore(settings).log_call(
        provider="openai",
        model="gpt-5.4-nano",
        mode="live",
        input_tokens=10,
        output_tokens=10,
        estimated_cost_usd=0.01,
        latency_ms=1,
        success=True,
    )

    result = await reconcile_provider_usage("openai", "all", settings, SyncStore(settings))
    assert result.status == "estimated"
    assert result.provider_reported_cost_usd is None


@pytest.mark.anyio
async def test_reconciliation_shows_dev_estimate_without_comparison(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("PROVIDER_USAGE_STORE_PATH", str(tmp_path / "provider_usage"))
    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    UsageStore(settings).log_call(
        provider="openai",
        model="gpt-5.4-nano",
        mode="live",
        input_tokens=10,
        output_tokens=10,
        estimated_cost_usd=0.01,
        actual_cost_usd=0.01,
        latency_ms=1,
        success=True,
    )
    SyncStore(settings).create_record(provider="openai", source="provider_official_api", provider_reported_cost_usd=0.0101)

    result = await reconcile_provider_usage("openai", "all", settings, SyncStore(settings))
    assert result.status == "provider_reported"
    assert result.safety_estimated_cost_usd == 0.01
    assert result.provider_reported_cost_usd == 0.0101
    assert "not comparable" not in " ".join(result.notes).lower()


@pytest.mark.anyio
async def test_provider_test_run_type_creates_no_files_or_commands(monkeypatch, tmp_path):
    monkeypatch.setenv("ALLOW_LIVE_CALLS", "true")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("PROVIDER_USAGE_STORE_PATH", str(tmp_path / "provider_usage"))
    from app.core.config import get_settings

    get_settings.cache_clear()

    async def fake_generate_with_provider(**kwargs):
        return (
            ProviderResponse(
                provider="gemini",
                model=kwargs["model"],
                text="live test ok",
                input_tokens=3,
                output_tokens=3,
                cached_tokens=0,
                estimated_cost_usd=0.00001,
                latency_ms=1,
                raw_metadata={"usage_source": "provider", "response_id": "resp-1"},
            ),
            "usage-log-1",
        )

    monkeypatch.setattr("app.orchestration.execution_engine.generate_with_provider", fake_generate_with_provider)
    record = await ExecutionEngine(get_settings()).execute_run(
        command="Run one tiny live provider test. Reply only: live test ok.",
        mode="live",
        run_type="provider_test",
        allow_file_writes=False,
        allow_safe_commands=False,
        allow_ceo_live=False,
        max_cost_usd=0.01,
    )

    assert record.run_type == "provider_test"
    assert record.project_files_created == []
    assert record.project_files_updated == []
    assert record.commands_run == []
    assert record.events[0].agent_name == "Provider Test Agent"
