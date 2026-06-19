from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.analytics.usage_analytics import UsageAnalytics
from app.core.config import Settings, get_settings
from app.storage.usage_store import UsageStore
from app.usage_sync.schemas import ProviderUsageRecord, UsageReconciliationResult
from app.usage_sync.sync_store import SyncStore

PROVIDERS = ("openai", "openrouter", "google", "exa")


async def reconcile_provider_usage(provider: str, time_range: str = "30d", settings: Settings | None = None, store: SyncStore | None = None) -> UsageReconciliationResult:
    settings = settings or get_settings()
    store = store or SyncStore(settings)
    local_rows = _local_rows(provider, time_range, settings, store)
    safety_estimate = round(sum(_effective_cost(row) for row in local_rows), 6)
    live_rows = [row for row in local_rows if _value(row, "mode") == "live" or isinstance(row, ProviderUsageRecord)]
    official = _official_records(provider, store)
    official_cost = _official_cost(provider, official)
    notes = _notes(provider, live_rows, official, store)

    if not live_rows and not official:
        status = "mock_only"
    elif live_rows and not official:
        status = "estimated"
    elif official_cost is not None:
        status = "provider_reported"
    else:
        status = "unavailable"

    return UsageReconciliationResult(
        provider=provider,
        range=time_range,
        scope="mixed",
        safety_estimated_cost_usd=safety_estimate,
        provider_reported_cost_usd=official_cost,
        status=status,
        last_synced_at=store.last_synced_at(provider),
        notes=notes,
    )


async def get_all_provider_reconciliation(time_range: str = "30d", settings: Settings | None = None, store: SyncStore | None = None) -> list[UsageReconciliationResult]:
    settings = settings or get_settings()
    store = store or SyncStore(settings)
    return [await reconcile_provider_usage(provider, time_range, settings, store) for provider in PROVIDERS]


def store_provider_response_usage(
    *,
    provider: str,
    model: str,
    run_id: str | None,
    request_id: str | None,
    response_id: str | None,
    generation_id: str | None = None,
    project_id: str | None = None,
    agent_name: str | None = None,
    requested_model: str | None = None,
    actual_model: str | None = None,
    openrouter_provider_name: str | None = None,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    reasoning_tokens: int | None = None,
    safety_estimated_cost_usd: float | None = None,
    provider_reported_cost_usd: float | None = None,
    raw: dict[str, Any] | None = None,
    settings: Settings | None = None,
    store: SyncStore | None = None,
) -> ProviderUsageRecord:
    store = store or SyncStore(settings)
    return store.create_record(
        provider=provider,
        source="provider_response",
        scope="run",
        run_id=run_id,
        project_id=project_id,
        agent_name=agent_name,
        request_id=request_id,
        response_id=response_id,
        generation_id=generation_id,
        requested_model=requested_model,
        actual_model=actual_model or model,
        model=actual_model or model,
        openrouter_provider_name=openrouter_provider_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
        total_tokens=input_tokens + output_tokens + (reasoning_tokens or 0),
        safety_estimated_cost_usd=safety_estimated_cost_usd,
        provider_reported_cost_usd=provider_reported_cost_usd,
        raw_usage_metadata=raw or {},
        raw=raw or {},
    )


def _local_rows(provider: str, time_range: str, settings: Settings, store: SyncStore) -> list:
    if provider == "exa":
        return [record for record in store.list_records("exa") if record.source == "provider_response"]
    rows = UsageAnalytics(UsageStore(settings), settings)._rows(time_range)
    aliases = {"google": {"google", "gemini"}, "openai": {"openai"}, "openrouter": {"openrouter"}}
    names = aliases.get(provider, {provider})
    return [row for row in rows if str(_value(row, "provider") or "").lower() in names]


def _official_records(provider: str, store: SyncStore) -> list[ProviderUsageRecord]:
    if provider == "openrouter":
        latest_balance = _latest_record([record for record in store.list_records("openrouter") if record.source == "provider_account_balance"])
        return [latest_balance] if latest_balance else []
    return [record for record in store.list_records(provider) if record.source == "provider_official_billing"]


def _notes(provider: str, live_rows: list, official: list[ProviderUsageRecord], store: SyncStore) -> list[str]:
    notes = []
    if not live_rows:
        notes.append("No live provider calls found for this provider in the selected range; dev/safety estimates remain separate from real totals.")
    if live_rows and not official:
        notes.append("Official provider data not available yet.")
    if provider == "openrouter" and official:
        notes.append("OpenRouter value is the latest account-balance snapshot, not summed history.")
    if provider in {"openai", "google"} and official:
        notes.append("Official provider billing is shown separately from dev/safety estimates.")
    message = store.status().get(provider, {}).get("message")
    if message:
        notes.append(str(message))
    return notes


def _official_cost(provider: str, records: list[ProviderUsageRecord]) -> float | None:
    if not records:
        return None
    if provider == "openrouter":
        latest = _latest_record(records)
        return latest.provider_reported_cost_usd if latest else None
    cost_values = [record.provider_reported_cost_usd for record in records if record.provider_reported_cost_usd is not None]
    return round(sum(cost_values), 6) if cost_values else None


def _latest_record(records: list[ProviderUsageRecord]) -> ProviderUsageRecord | None:
    if not records:
        return None
    return max(records, key=_record_sort_time)


def _record_sort_time(record: ProviderUsageRecord) -> datetime:
    for value in (record.local_created_at, record.created_at, record.provider_created_at, record.usage_end_time):
        parsed = _parse_datetime(value)
        if parsed:
            return parsed
    return datetime.min.replace(tzinfo=UTC)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _effective_cost(row) -> float:
    if isinstance(row, ProviderUsageRecord):
        return float(row.provider_reported_cost_usd or row.safety_estimated_cost_usd or 0)
    actual = _value(row, "actual_cost_usd")
    if actual is not None:
        return float(actual)
    total = _value(row, "total_cost_usd")
    return float(total if total is not None else _value(row, "estimated_cost_usd") or 0)


def _value(row, field: str) -> Any:
    if isinstance(row, ProviderUsageRecord):
        return getattr(row, field, None)
    return row[field] if field in row.keys() else None
