from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.usage_sync.schemas import ProviderUsageRecord


class SyncStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = self.settings.provider_usage_path
        self.records_path = self.root / "records.json"
        self.status_path = self.root / "status.json"
        self.root.mkdir(parents=True, exist_ok=True)

    def save_records(self, records: list[ProviderUsageRecord]) -> list[ProviderUsageRecord]:
        existing = self.list_records()
        by_id = {record.id: record for record in existing}
        for record in records:
            by_id[record.id] = record
        ordered = sorted(by_id.values(), key=lambda record: record.created_at, reverse=True)
        self._write_json(self.records_path, [record.model_dump() for record in ordered])
        return records

    def create_record(self, **data: Any) -> ProviderUsageRecord:
        now = datetime.now(UTC).isoformat()
        raw = _sanitize_raw(data.pop("raw", {}))
        data.setdefault("local_created_at", now)
        data = _normalize_record_payload(data)
        record = ProviderUsageRecord(
            id=data.pop("id", str(uuid.uuid4())),
            created_at=data.pop("created_at", now),
            raw=raw,
            **data,
        )
        self.save_records([record])
        return record

    def list_records(self, provider: str | None = None, limit: int | None = None) -> list[ProviderUsageRecord]:
        rows = self._read_json(self.records_path, [])
        records = [ProviderUsageRecord(**_normalize_record_payload(row)) for row in rows]
        if provider:
            records = [record for record in records if record.provider.lower() == provider.lower()]
        if limit is not None:
            records = records[: max(0, limit)]
        return records

    def update_status(self, provider: str, *, status: str, message: str | None = None, **extra: Any) -> dict[str, Any]:
        state = self.status()
        current = state.get(provider, {})
        current.update(
            {
                "status": status,
                "message": message,
                "last_synced_at": datetime.now(UTC).isoformat(),
                **extra,
            }
        )
        state[provider] = current
        self._write_json(self.status_path, state)
        return current

    def status(self) -> dict[str, Any]:
        return self._read_json(self.status_path, {})

    def last_synced_at(self, provider: str) -> str | None:
        value = self.status().get(provider, {}).get("last_synced_at")
        return str(value) if value else None

    def _read_json(self, path: Path, fallback: Any) -> Any:
        if not path.exists():
            return fallback
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return fallback

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _sanitize_raw(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(secret_word in lowered for secret_word in ("key", "token", "authorization", "credential", "secret")):
                sanitized[key] = "[redacted]"
            else:
                sanitized[key] = _sanitize_raw(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_raw(item) for item in value]
    return value


def _normalize_record_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    source_map = {
        "local_estimate": "safety_estimate_dev_only",
        "provider_official_api": "provider_official_billing",
        "billing_export": "provider_official_billing",
    }
    if payload.get("provider") == "openrouter" and payload.get("service") == "credits":
        payload["source"] = "provider_account_balance"
    elif payload.get("source") in source_map:
        payload["source"] = source_map[payload["source"]]
    if "local_estimated_cost_usd" in payload and "safety_estimated_cost_usd" not in payload:
        payload["safety_estimated_cost_usd"] = payload.pop("local_estimated_cost_usd")
    if payload.get("source") == "provider_response":
        payload.setdefault("scope", "run")
    elif payload.get("source") == "provider_generation_lookup":
        payload.setdefault("scope", "run")
    elif payload.get("source") == "provider_account_balance":
        payload.setdefault("scope", "account")
    elif payload.get("source") == "provider_official_billing":
        payload.setdefault("scope", "account_or_project")
    else:
        payload.setdefault("scope", "unknown")
    if payload.get("actual_model") is None and payload.get("model"):
        payload["actual_model"] = payload["model"]
    if payload.get("model") is None and payload.get("actual_model"):
        payload["model"] = payload["actual_model"]
    payload.setdefault("raw_usage_metadata", {})
    payload.setdefault("raw_billing_metadata", {})
    return payload
