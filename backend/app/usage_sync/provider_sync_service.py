from __future__ import annotations

from typing import Any
from datetime import UTC, datetime, timedelta

from app.core.config import Settings, get_settings
from app.usage_sync.google_billing_sync import sync_google_billing
from app.usage_sync.exa_usage_sync import sync_exa_usage
from app.usage_sync.openai_usage_sync import sync_openai_usage
from app.usage_sync.openrouter_usage_sync import sync_openrouter_credits
from app.usage_sync.reconciliation_service import get_all_provider_reconciliation
from app.usage_sync.sync_store import SyncStore


class ProviderSyncService:
    def __init__(self, settings: Settings | None = None, store: SyncStore | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = store or SyncStore(self.settings)

    async def status(self) -> dict[str, Any]:
        state = self.store.status()
        return {
            "openai": {
                "enabled": self.settings.enable_openai_official_usage_sync,
                "admin_key_configured": bool(self.settings.openai_admin_api_key),
                "last_synced_at": state.get("openai", {}).get("last_synced_at"),
                "status": state.get("openai", {}).get("status", self._default_status(self.settings.enable_openai_official_usage_sync, bool(self.settings.openai_admin_api_key))),
                "message": state.get("openai", {}).get("message"),
            },
            "openrouter": {
                "enabled": self.settings.enable_openrouter_official_usage_sync,
                "management_key_configured": bool(self.settings.openrouter_management_key),
                "last_synced_at": state.get("openrouter", {}).get("last_synced_at"),
                "status": state.get("openrouter", {}).get("status", self._default_status(self.settings.enable_openrouter_official_usage_sync, bool(self.settings.openrouter_management_key))),
                "message": state.get("openrouter", {}).get("message"),
            },
            "google": {
                "enabled": self.settings.enable_google_billing_sync,
                "credentials_configured": bool(self.settings.google_application_credentials),
                "project_id": self.settings.google_cloud_project_id,
                "dataset": self.settings.google_billing_bigquery_dataset,
                "location": self.settings.google_billing_location,
                "tables_found": state.get("google", {}).get("tables_found", 0),
                "last_synced_at": state.get("google", {}).get("last_synced_at"),
                "status": state.get("google", {}).get("status", self._default_status(self.settings.enable_google_billing_sync, bool(self.settings.google_application_credentials))),
                "message": state.get("google", {}).get("message"),
            },
            "exa": {
                "enabled": self.settings.enable_exa_official_usage_sync,
                "api_key_configured": bool(self.settings.exa_api_key),
                "service_key_configured": bool(self.settings.exa_service_api_key),
                "api_key_id_configured": bool(self.settings.exa_api_key_id),
                "last_synced_at": state.get("exa", {}).get("last_synced_at"),
                "status": state.get("exa", {}).get(
                    "status",
                    self._default_status(
                        self.settings.enable_exa_official_usage_sync,
                        bool(self.settings.exa_service_api_key and self.settings.exa_api_key_id),
                    ),
                ),
                "message": state.get("exa", {}).get("message"),
            },
        }

    async def sync_all(self, time_range: str = "30d") -> dict[str, Any]:
        openai_records = await sync_openai_usage(time_range, self.settings, self.store)
        openrouter_record = await sync_openrouter_credits(self.settings, self.store)
        google_records = await sync_google_billing(time_range, self.settings, self.store)
        exa_records = await sync_exa_usage(time_range, self.settings, self.store)
        return {
            "status": await self.status(),
            "synced": {
                "openai": len(openai_records),
                "openrouter": 1 if openrouter_record else 0,
                "google": len(google_records),
                "exa": len(exa_records),
            },
            "note": "Official usage sync may query BigQuery. No live model calls are made.",
        }

    async def sync_after_live_run(self, time_range: str = "30d") -> dict[str, Any]:
        if not self.settings.auto_sync_official_usage_after_live_run:
            return {"skipped": True, "reason": "AUTO_SYNC_OFFICIAL_USAGE_AFTER_LIVE_RUN=false"}
        if not self._cooldown_elapsed():
            return {"skipped": True, "reason": "Official usage sync cooldown active."}
        return await self.sync_all(time_range)

    async def summary(self, time_range: str = "30d") -> dict[str, Any]:
        reconciliation = await get_all_provider_reconciliation(time_range, self.settings, self.store)
        return {
            "range": time_range,
            "status": await self.status(),
            "reconciliation": [item.model_dump() for item in reconciliation],
        }

    def _default_status(self, enabled: bool, configured: bool) -> str:
        if not enabled:
            return "disabled"
        if not configured:
            return "unavailable"
        return "not_synced"

    def _cooldown_elapsed(self) -> bool:
        latest: datetime | None = None
        for value in self.store.status().values():
            timestamp = value.get("last_synced_at") if isinstance(value, dict) else None
            if not timestamp:
                continue
            try:
                parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            except ValueError:
                continue
            latest = parsed if latest is None or parsed > latest else latest
        if latest is None:
            return True
        cooldown = timedelta(minutes=max(0, self.settings.official_usage_sync_cooldown_minutes))
        return datetime.now(UTC) - latest >= cooldown
