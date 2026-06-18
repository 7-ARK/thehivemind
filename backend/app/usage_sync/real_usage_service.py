from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings, get_settings
from app.usage_sync.schemas import ProviderUsageRecord
from app.usage_sync.sync_store import SyncStore

RUN_LEVEL_SOURCES = {"provider_response", "provider_generation_lookup"}
OFFICIAL_SOURCES = {"provider_official_billing", "provider_account_balance"}
DEV_SOURCES = {"mock_dev_only", "safety_estimate_dev_only"}


class RealUsageService:
    def __init__(self, settings: Settings | None = None, store: SyncStore | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = store or SyncStore(self.settings)

    def summary(self, include_dev_estimates: bool = False) -> dict[str, Any]:
        run_records = self._run_records(include_dev_estimates)
        official_cards = self._official_cards()
        return {
            "run_level_provider_cost_usd": round(sum(record.provider_reported_cost_usd or 0 for record in run_records), 6),
            "run_level_tokens": sum(record.total_tokens or 0 for record in run_records),
            "run_level_calls": len(run_records),
            "official_billing_cost_usd": round(sum(card["provider_reported_cost_usd"] or 0 for card in official_cards if card["source"] == "provider_official_billing"), 6),
            "account_balance_records": len([card for card in official_cards if card["source"] == "provider_account_balance"]),
            "providers": sorted({record.provider for record in run_records} | {card["provider"] for card in official_cards}),
            "dev_estimates_hidden": not include_dev_estimates,
            "note": "Run totals use provider_response and provider_generation_lookup records. Official billing is aggregated by provider; account balances use the latest snapshot only.",
        }

    def provider_responses(self, include_dev_estimates: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        records = self._run_records(include_dev_estimates)[:limit]
        return [self._run_row(record) for record in records]

    def runs(self, include_dev_estimates: bool = False) -> dict[str, Any]:
        grouped: dict[str, list[ProviderUsageRecord]] = defaultdict(list)
        for record in self._run_records(include_dev_estimates):
            grouped[record.run_id or "unassigned"].append(record)
        return {
            "runs": [
                {
                    "run_id": run_id,
                    "project_id": _first(records, "project_id"),
                    "providers": sorted({record.provider for record in records}),
                    "models": sorted({record.actual_model or record.model or "unknown" for record in records}),
                    "provider_reported_cost_usd": round(sum(record.provider_reported_cost_usd or 0 for record in records), 6),
                    "total_tokens": sum(record.total_tokens or 0 for record in records),
                    "calls": len(records),
                    "sources": sorted({record.source for record in records}),
                    "latest_at": max((record.local_created_at or record.created_at for record in records), default=None),
                }
                for run_id, records in grouped.items()
            ]
        }

    def models(self, include_dev_estimates: bool = False) -> dict[str, Any]:
        grouped: dict[tuple[str, str, str, str, str], list[ProviderUsageRecord]] = defaultdict(list)
        for record in self._run_records(include_dev_estimates):
            key = (
                record.provider,
                record.actual_model or record.model or "unknown",
                record.openrouter_provider_name or "",
                record.agent_name or "unassigned",
                record.run_id or "unassigned",
            )
            grouped[key].append(record)
        return {
            "models": [
                {
                    "provider": provider,
                    "model": model,
                    "provider_name": provider_name or None,
                    "agent_name": agent_name,
                    "run_id": run_id,
                    "provider_reported_cost_usd": round(sum(record.provider_reported_cost_usd or 0 for record in records), 6),
                    "input_tokens": sum(record.input_tokens or 0 for record in records),
                    "output_tokens": sum(record.output_tokens or 0 for record in records),
                    "cached_tokens": sum(record.cached_tokens or 0 for record in records),
                    "reasoning_tokens": sum(record.reasoning_tokens or 0 for record in records),
                    "total_tokens": sum(record.total_tokens or 0 for record in records),
                    "calls": len(records),
                }
                for (provider, model, provider_name, agent_name, run_id), records in grouped.items()
            ]
        }

    def providers(self, include_dev_estimates: bool = False) -> dict[str, Any]:
        grouped: dict[str, list[ProviderUsageRecord]] = defaultdict(list)
        for record in self._run_records(include_dev_estimates):
            grouped[record.provider].append(record)
        return {
            "providers": [
                {
                    "provider": provider,
                    "provider_reported_cost_usd": round(sum(record.provider_reported_cost_usd or 0 for record in records), 6),
                    "total_tokens": sum(record.total_tokens or 0 for record in records),
                    "calls": len(records),
                    "sources": sorted({record.source for record in records}),
                }
                for provider, records in grouped.items()
            ]
        }

    def openrouter_breakdown(self) -> dict[str, Any]:
        records = [record for record in self._run_records(False) if record.provider == "openrouter"]
        return self.models(False) | {"records": [self._run_row(record) for record in records]}

    def account_billing(self) -> dict[str, Any]:
        return {
            "records": self._official_cards(),
            "note": "Provider cards are aggregated for the dashboard. OpenRouter is the latest account-balance snapshot; OpenAI and Google/Gemini are official billing/export totals.",
        }

    def _run_records(self, include_dev_estimates: bool) -> list[ProviderUsageRecord]:
        allowed = set(RUN_LEVEL_SOURCES)
        if include_dev_estimates:
            allowed.update(DEV_SOURCES)
        return [record for record in self.store.list_records() if record.source in allowed and (record.scope == "run" or include_dev_estimates)]

    def _official_records(self) -> list[ProviderUsageRecord]:
        return [record for record in self.store.list_records() if record.source in OFFICIAL_SOURCES]

    def _official_cards(self) -> list[dict[str, Any]]:
        records = self._official_records()
        cards: list[dict[str, Any]] = []

        openrouter_balance = _latest_record(
            [record for record in records if record.provider == "openrouter" and record.source == "provider_account_balance"]
        )
        if openrouter_balance:
            row = self._official_row(openrouter_balance)
            row["id"] = "openrouter-account-balance-latest"
            row["raw_record_count"] = len(
                [record for record in records if record.provider == "openrouter" and record.source == "provider_account_balance"]
            )
            row["note"] = "Latest OpenRouter account-level total usage/credits snapshot. This is not run-level spend."
            cards.append(row)

        for provider in ("openai", "google"):
            provider_records = [
                record
                for record in records
                if record.provider == provider and record.source == "provider_official_billing"
            ]
            if provider_records:
                cards.append(_aggregate_official_billing(provider, provider_records))

        return sorted(cards, key=lambda card: {"openrouter": 0, "openai": 1, "google": 2}.get(card["provider"], 99))

    def _run_row(self, record: ProviderUsageRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "run_id": record.run_id,
            "project_id": record.project_id,
            "provider": record.provider,
            "requested_model": record.requested_model,
            "actual_model": record.actual_model or record.model,
            "provider_name": record.openrouter_provider_name,
            "agent_name": record.agent_name,
            "input_tokens": record.input_tokens or 0,
            "output_tokens": record.output_tokens or 0,
            "cached_tokens": record.cached_tokens or 0,
            "reasoning_tokens": record.reasoning_tokens or 0,
            "total_tokens": record.total_tokens or 0,
            "provider_reported_cost_usd": record.provider_reported_cost_usd,
            "source": record.source,
            "sync_status": record.sync_status,
            "timestamp": record.provider_created_at or record.local_created_at or record.created_at,
        }

    def _official_row(self, record: ProviderUsageRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "provider": record.provider,
            "source": record.source,
            "scope": record.scope,
            "project_id": record.project_id,
            "service": record.service,
            "sku": record.sku,
            "provider_reported_cost_usd": record.provider_reported_cost_usd,
            "currency": record.currency,
            "usage_start_time": record.usage_start_time,
            "usage_end_time": record.usage_end_time,
            "created_at": record.created_at,
            "note": _official_note(record),
        }


def _first(records: list[ProviderUsageRecord], field: str) -> Any:
    for record in records:
        value = getattr(record, field)
        if value:
            return value
    return None


def _official_note(record: ProviderUsageRecord) -> str:
    if record.provider == "openrouter" and record.source == "provider_account_balance":
        return "Account-level total usage / credits, not TheHiveMind run-level spend."
    if record.provider == "google":
        return "Delayed Google Cloud Billing export. May lag behind live Gemini calls."
    if record.provider == "openai":
        return "Official OpenAI organization/project billing. May be delayed or aggregated."
    return "Official provider data."


def _aggregate_official_billing(provider: str, records: list[ProviderUsageRecord]) -> dict[str, Any]:
    latest = _latest_record(records)
    cost_values = [record.provider_reported_cost_usd for record in records if record.provider_reported_cost_usd is not None]
    cost = round(sum(cost_values), 6) if cost_values else None
    return {
        "id": f"{provider}-official-billing-aggregate",
        "provider": provider,
        "source": "provider_official_billing",
        "scope": "account_or_project",
        "project_id": _first(records, "project_id"),
        "service": _first(records, "service"),
        "sku": None,
        "provider_reported_cost_usd": cost,
        "currency": _first(records, "currency") or "USD",
        "usage_start_time": min((record.usage_start_time for record in records if record.usage_start_time), default=None),
        "usage_end_time": max((record.usage_end_time for record in records if record.usage_end_time), default=None),
        "created_at": latest.created_at if latest else records[0].created_at,
        "raw_record_count": len(records),
        "note": _aggregate_note(provider, len(records)),
    }


def _aggregate_note(provider: str, count: int) -> str:
    if provider == "openai":
        return f"Aggregated official OpenAI organization/project billing from {count} synced row(s). May be delayed by provider reporting."
    if provider == "google":
        return f"Aggregated Google/Gemini billing export from {count} synced row(s). BigQuery billing export can lag behind live calls."
    return f"Aggregated official provider billing from {count} synced row(s)."


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
