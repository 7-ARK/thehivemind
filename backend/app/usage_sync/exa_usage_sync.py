from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.usage_sync.range_utils import range_bounds
from app.usage_sync.schemas import ProviderUsageRecord, UsageReconciliationResult
from app.usage_sync.sync_store import SyncStore


EXA_USAGE_URL = "https://admin-api.exa.ai/team-management/api-keys/{id}/usage"


async def sync_exa_usage(time_range: str = "30d", settings: Settings | None = None, store: SyncStore | None = None) -> list[ProviderUsageRecord]:
    active_settings = settings or get_settings()
    sync_store = store or SyncStore(active_settings)
    if not active_settings.enable_exa_official_usage_sync:
        sync_store.update_status("exa", status="disabled", message="ENABLE_EXA_OFFICIAL_USAGE_SYNC=false")
        return []
    if not active_settings.exa_service_api_key or not active_settings.exa_api_key_id:
        sync_store.update_status("exa", status="unavailable", message="EXA_SERVICE_API_KEY and EXA_API_KEY_ID are required for official Exa usage sync.")
        return []

    start, end = range_bounds(time_range)
    params: dict[str, Any] = {"end_date": end.isoformat(), "group_by": "day"}
    if start:
        params["start_date"] = start.isoformat()
    url = EXA_USAGE_URL.format(id=active_settings.exa_api_key_id)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers={"x-api-key": active_settings.exa_service_api_key}, params=params)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        sync_store.update_status("exa", status="error", message=f"Exa official usage sync failed: {exc}")
        return []

    record = sync_store.create_record(
        id=f"exa-official-{active_settings.exa_api_key_id}-{time_range}",
        provider="exa",
        source="provider_official_billing",
        scope="account",
        api_key_id=str(payload.get("api_key_id") or active_settings.exa_api_key_id),
        service="exa",
        sku="api_key_usage",
        provider_reported_cost_usd=_as_float(payload.get("total_cost_usd")),
        currency="USD",
        sync_status="ok",
        usage_start_time=(payload.get("period") or {}).get("start"),
        usage_end_time=(payload.get("period") or {}).get("end"),
        raw_billing_metadata={
            "api_key_name": payload.get("api_key_name"),
            "team_id": payload.get("team_id"),
            "cost_breakdown": payload.get("cost_breakdown", []),
            "metadata": payload.get("metadata", {}),
        },
        raw=payload,
        created_at=datetime.now(UTC).isoformat(),
    )
    sync_store.update_status("exa", status="ok", message="Synced Exa official API-key usage.", records=1)
    return [record]


async def get_exa_official_summary(time_range: str = "30d", settings: Settings | None = None, store: SyncStore | None = None) -> UsageReconciliationResult:
    active_settings = settings or get_settings()
    sync_store = store or SyncStore(active_settings)
    records = [
        record
        for record in sync_store.list_records(provider="exa")
        if record.source == "provider_official_billing"
    ]
    latest = records[0] if records else None
    if not active_settings.enable_exa_official_usage_sync:
        status = "unavailable"
        notes = ["Exa official usage sync is disabled."]
    elif not active_settings.exa_service_api_key or not active_settings.exa_api_key_id:
        status = "unavailable"
        notes = ["Add EXA_SERVICE_API_KEY and EXA_API_KEY_ID to enable official Exa API-key usage sync."]
    elif latest:
        status = "provider_reported"
        notes = ["Official Exa API-key usage is account/key-level billing, not exact TheHiveMind run-level spend."]
    else:
        status = "unavailable"
        notes = ["No Exa official usage records have been synced yet."]
    return UsageReconciliationResult(
        provider="exa",
        range=time_range,
        scope="account",
        safety_estimated_cost_usd=_exa_safety_estimate(sync_store),
        provider_reported_cost_usd=latest.provider_reported_cost_usd if latest else None,
        status=status,
        last_synced_at=sync_store.last_synced_at("exa"),
        notes=notes,
    )


def _exa_safety_estimate(store: SyncStore) -> float:
    return round(
        sum(record.safety_estimated_cost_usd or 0 for record in store.list_records(provider="exa") if record.source == "provider_response"),
        6,
    )


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
