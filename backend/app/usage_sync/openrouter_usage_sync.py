from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.usage_sync.schemas import ProviderUsageRecord, UsageReconciliationResult
from app.usage_sync.sync_store import SyncStore

OPENROUTER_CREDITS_URL = "https://openrouter.ai/api/v1/credits"
OPENROUTER_GENERATION_URL = "https://openrouter.ai/api/v1/generation"


async def sync_openrouter_generation(
    *,
    generation_id: str,
    run_id: str | None,
    project_id: str | None = None,
    agent_name: str | None = None,
    requested_model: str | None = None,
    settings: Settings | None = None,
    store: SyncStore | None = None,
) -> ProviderUsageRecord | None:
    settings = settings or get_settings()
    store = store or SyncStore(settings)
    key = settings.openrouter_api_key or settings.openrouter_management_key
    if not key:
        return store.create_record(
            provider="openrouter",
            source="provider_generation_lookup",
            scope="run",
            run_id=run_id,
            project_id=project_id,
            agent_name=agent_name,
            requested_model=requested_model,
            generation_id=generation_id,
            sync_status="pending",
            raw_usage_metadata={"message": "OpenRouter generation lookup pending: key missing."},
        )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                OPENROUTER_GENERATION_URL,
                headers={"Authorization": f"Bearer {key}"},
                params={"id": generation_id},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        return store.create_record(
            provider="openrouter",
            source="provider_generation_lookup",
            scope="run",
            run_id=run_id,
            project_id=project_id,
            agent_name=agent_name,
            requested_model=requested_model,
            generation_id=generation_id,
            sync_status="pending",
            raw_usage_metadata={"message": f"OpenRouter generation lookup pending: {exc}"},
        )

    data = payload.get("data") or payload
    tokens_prompt = _int(data.get("tokens_prompt") or data.get("native_tokens_prompt"))
    tokens_completion = _int(data.get("tokens_completion") or data.get("native_tokens_completion"))
    reasoning = _int(data.get("native_tokens_reasoning"))
    cached = _int(data.get("native_tokens_cached"))
    cost = _float(data.get("total_cost") or data.get("usage") or data.get("upstream_inference_cost"))
    model = data.get("model") or requested_model
    return store.create_record(
        provider="openrouter",
        source="provider_generation_lookup",
        scope="run",
        run_id=run_id,
        project_id=project_id,
        agent_name=agent_name,
        requested_model=requested_model,
        actual_model=model,
        model=model,
        openrouter_provider_name=data.get("provider_name") or data.get("provider"),
        request_id=data.get("request_id"),
        response_id=generation_id,
        generation_id=generation_id,
        input_tokens=tokens_prompt,
        output_tokens=tokens_completion,
        cached_tokens=cached,
        reasoning_tokens=reasoning,
        total_tokens=tokens_prompt + tokens_completion + reasoning,
        provider_reported_cost_usd=cost,
        sync_status="synced",
        provider_created_at=data.get("created_at"),
        raw_usage_metadata={
            "router": data.get("router"),
            "usage": data.get("usage"),
            "total_cost": data.get("total_cost"),
            "upstream_inference_cost": data.get("upstream_inference_cost"),
            "provider_response": payload,
        },
        raw={"provider_response": payload},
    )


async def sync_openrouter_credits(settings: Settings | None = None, store: SyncStore | None = None) -> ProviderUsageRecord | None:
    settings = settings or get_settings()
    store = store or SyncStore(settings)
    if not settings.enable_openrouter_official_usage_sync:
        store.update_status("openrouter", status="disabled", message="OpenRouter official usage sync is disabled.")
        return None
    if not settings.openrouter_management_key:
        store.update_status("openrouter", status="unavailable", message="OpenRouter official credit sync unavailable: management key missing.")
        return None

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(OPENROUTER_CREDITS_URL, headers={"Authorization": f"Bearer {settings.openrouter_management_key}"})
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        message = "OpenRouter official credit sync unavailable: management key missing or unauthorized."
        store.update_status("openrouter", status="unauthorized" if exc.response.status_code in {401, 403} else "error", message=message)
        return None
    except Exception as exc:
        store.update_status("openrouter", status="error", message=f"OpenRouter credit sync failed: {exc}")
        return None

    data = payload.get("data") or payload
    total_credits = _float(data.get("total_credits"))
    total_usage = _float(data.get("total_usage"))
    remaining = None if total_credits is None or total_usage is None else round(total_credits - total_usage, 6)
    record = store.create_record(
        provider="openrouter",
        source="provider_account_balance",
        scope="account",
        provider_reported_cost_usd=total_usage,
        service="credits",
        raw={"total_credits": total_credits, "total_usage": total_usage, "remaining_credits": remaining, "provider_response": payload},
    )
    store.update_status("openrouter", status="ok", message="Synced OpenRouter official credits.", remaining_credits=remaining)
    return record


async def get_openrouter_official_summary(time_range: str = "30d", settings: Settings | None = None, store: SyncStore | None = None) -> UsageReconciliationResult:
    store = store or SyncStore(settings)
    records = [record for record in store.list_records("openrouter") if record.source == "provider_account_balance"]
    latest = records[0] if records else None
    return UsageReconciliationResult(
        provider="openrouter",
        range=time_range,
        scope="account",
        safety_estimated_cost_usd=0,
        provider_reported_cost_usd=latest.provider_reported_cost_usd if latest else None,
        status="provider_reported" if latest else "unavailable",
        last_synced_at=store.last_synced_at("openrouter"),
        notes=[] if latest else ["OpenRouter official credit data is not available yet."],
    )


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
