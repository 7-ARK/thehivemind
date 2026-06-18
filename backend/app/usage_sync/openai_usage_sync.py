from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.usage_sync.range_utils import unix_bounds
from app.usage_sync.schemas import ProviderUsageRecord, UsageReconciliationResult
from app.usage_sync.sync_store import SyncStore

OPENAI_COSTS_URL = "https://api.openai.com/v1/organization/costs"
OPENAI_COMPLETIONS_USAGE_URL = "https://api.openai.com/v1/organization/usage/completions"


async def sync_openai_usage(time_range: str = "30d", settings: Settings | None = None, store: SyncStore | None = None) -> list[ProviderUsageRecord]:
    settings = settings or get_settings()
    store = store or SyncStore(settings)
    if not settings.enable_openai_official_usage_sync:
        store.update_status("openai", status="disabled", message="OpenAI official usage sync is disabled.")
        return []
    if not settings.openai_admin_api_key:
        store.update_status("openai", status="unavailable", message="OpenAI official sync unavailable: admin key missing or unauthorized.")
        return []

    start_time, end_time = unix_bounds(time_range)
    headers = {"Authorization": f"Bearer {settings.openai_admin_api_key}"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            costs = await _get_json(
                client,
                OPENAI_COSTS_URL,
                headers=headers,
                params=[
                    ("start_time", start_time),
                    ("bucket_width", "1d"),
                    ("limit", 31),
                ],
            )
            usage = await _get_json(
                client,
                OPENAI_COMPLETIONS_USAGE_URL,
                headers=headers,
                params=[
                    ("start_time", start_time),
                    ("bucket_width", "1d"),
                    ("limit", 31),
                ],
            )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403}:
            message = "OpenAI official sync unavailable: admin key missing or unauthorized."
            store.update_status("openai", status="unauthorized", message=message)
            return []
        store.update_status("openai", status="error", message=f"OpenAI usage sync failed with HTTP {exc.response.status_code}.")
        return []
    except Exception as exc:
        store.update_status("openai", status="error", message=f"OpenAI usage sync failed: {exc}")
        return []

    records = _normalize_cost_records(costs, time_range) + _normalize_usage_records(usage, time_range)
    store.save_records(records)
    store.update_status("openai", status="ok", message=f"Synced {len(records)} OpenAI official usage records.")
    return records


async def get_openai_official_summary(time_range: str = "30d", settings: Settings | None = None, store: SyncStore | None = None) -> UsageReconciliationResult:
    store = store or SyncStore(settings)
    records = [record for record in store.list_records("openai") if record.source == "provider_official_billing"]
    total = round(sum(record.provider_reported_cost_usd or 0 for record in records), 6)
    status = "provider_reported" if records else "unavailable"
    notes = [] if records else ["OpenAI official provider data is not available yet."]
    return UsageReconciliationResult(
        provider="openai",
        range=time_range,
        scope="account_or_project",
        safety_estimated_cost_usd=0,
        provider_reported_cost_usd=total if records else None,
        status=status,
        last_synced_at=store.last_synced_at("openai"),
        notes=notes,
    )


async def _get_json(client: httpx.AsyncClient, url: str, *, headers: dict[str, str], params: list[tuple[str, Any]]) -> dict[str, Any]:
    response = await client.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()


def _normalize_cost_records(payload: dict[str, Any], time_range: str) -> list[ProviderUsageRecord]:
    records = []
    for bucket in payload.get("data") or []:
        for result in bucket.get("results") or []:
            amount = result.get("amount") or {}
            cost = _float(amount.get("value") if isinstance(amount, dict) else result.get("cost"))
            records.append(
                ProviderUsageRecord(
                    id=f"openai-cost-{bucket.get('start_time')}-{bucket.get('end_time')}-{len(records)}",
                    provider="openai",
                    source="provider_official_billing",
                    scope="account_or_project",
                    project_id=result.get("project_id"),
                    api_key_id=result.get("api_key_id"),
                    service=result.get("line_item"),
                    provider_reported_cost_usd=cost,
                    currency=(amount.get("currency") if isinstance(amount, dict) else None) or "USD",
                    usage_start_time=_unix_to_iso(bucket.get("start_time")),
                    usage_end_time=_unix_to_iso(bucket.get("end_time")),
                    raw_billing_metadata={"range": time_range, "bucket": bucket, "result": result},
                    raw={"range": time_range, "bucket": bucket, "result": result},
                    created_at=datetime.now(UTC).isoformat(),
                )
            )
    return records


def _normalize_usage_records(payload: dict[str, Any], time_range: str) -> list[ProviderUsageRecord]:
    records = []
    for bucket in payload.get("data") or []:
        for result in bucket.get("results") or []:
            input_tokens = _int(result.get("input_tokens"))
            output_tokens = _int(result.get("output_tokens"))
            cached_tokens = _int(result.get("input_cached_tokens"))
            records.append(
                ProviderUsageRecord(
                    id=f"openai-usage-{bucket.get('start_time')}-{bucket.get('end_time')}-{len(records)}",
                    provider="openai",
                    source="provider_official_billing",
                    scope="account_or_project",
                    project_id=result.get("project_id"),
                    api_key_id=result.get("api_key_id"),
                    model=result.get("model"),
                    actual_model=result.get("model"),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_tokens=cached_tokens,
                    total_tokens=input_tokens + output_tokens,
                    usage_start_time=_unix_to_iso(bucket.get("start_time")),
                    usage_end_time=_unix_to_iso(bucket.get("end_time")),
                    raw={"range": time_range, "bucket": bucket, "result": result},
                    created_at=datetime.now(UTC).isoformat(),
                )
            )
    return records


def _unix_to_iso(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _float(value: Any) -> float | None:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
