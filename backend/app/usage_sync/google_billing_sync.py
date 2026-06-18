from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings, get_settings
from app.usage_sync.range_utils import range_bounds
from app.usage_sync.schemas import ProviderUsageRecord, UsageReconciliationResult
from app.usage_sync.sync_store import SyncStore


async def list_google_billing_tables(settings: Settings | None = None, store: SyncStore | None = None) -> list[str]:
    settings = settings or get_settings()
    store = store or SyncStore(settings)
    if not settings.enable_google_billing_sync:
        store.update_status("google", status="disabled", message="Google billing sync is disabled.")
        return []
    if not _google_configured(settings):
        store.update_status("google", status="unavailable", message="Google billing sync unavailable: credentials, project, or dataset missing.")
        return []
    try:
        from google.cloud import bigquery
    except ImportError:
        store.update_status("google", status="unavailable", message="Google billing sync unavailable: google-cloud-bigquery is not installed.")
        return []

    try:
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", settings.google_application_credentials)
        client = bigquery.Client(project=settings.google_cloud_project_id, location=settings.google_billing_location)
        dataset_ref = bigquery.DatasetReference(settings.google_cloud_project_id, settings.google_billing_bigquery_dataset)
        tables = [table.table_id for table in client.list_tables(dataset_ref)]
    except Exception as exc:
        store.update_status("google", status="error", message=f"Google billing table lookup failed: {exc}", tables_found=0)
        return []

    status = "ok" if tables else "waiting_for_tables"
    message = None if tables else "Google billing export enabled, but BigQuery tables are not available yet. Try again later."
    store.update_status("google", status=status, message=message, tables_found=len(tables))
    return tables


async def sync_google_billing(time_range: str = "30d", settings: Settings | None = None, store: SyncStore | None = None) -> list[ProviderUsageRecord]:
    settings = settings or get_settings()
    store = store or SyncStore(settings)
    tables = await list_google_billing_tables(settings, store)
    if not tables:
        return []
    try:
        from google.cloud import bigquery
    except ImportError:
        return []

    table_id = _pick_billing_table(tables)
    full_table = f"`{settings.google_cloud_project_id}.{settings.google_billing_bigquery_dataset}.{table_id}`"
    start, end = range_bounds(time_range)
    start_param = (start or datetime(1970, 1, 1, tzinfo=UTC)).date().isoformat()
    end_param = end.date().isoformat()
    query = f"""
        SELECT
          service.description AS service,
          sku.description AS sku,
          project.id AS project_id,
          currency,
          SUM(cost) AS cost
        FROM {full_table}
        WHERE DATE(usage_start_time) >= @start_date
          AND DATE(usage_start_time) <= @end_date
        GROUP BY service, sku, project_id, currency
        ORDER BY cost DESC
        LIMIT 100
    """
    try:
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", settings.google_application_credentials)
        client = bigquery.Client(project=settings.google_cloud_project_id, location=settings.google_billing_location)
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("start_date", "DATE", start_param),
                bigquery.ScalarQueryParameter("end_date", "DATE", end_param),
            ]
        )
        rows = list(client.query(query, job_config=job_config))
    except Exception as exc:
        store.update_status("google", status="error", message=f"Google billing query failed: {exc}", tables_found=len(tables))
        return []

    records = [
        ProviderUsageRecord(
            id=f"google-billing-{table_id}-{index}-{datetime.now(UTC).timestamp()}",
            provider="google",
            source="provider_official_billing",
            scope="account_or_project",
            project_id=getattr(row, "project_id", None),
            service=getattr(row, "service", None),
            sku=getattr(row, "sku", None),
            provider_reported_cost_usd=_float(getattr(row, "cost", None)),
            currency=getattr(row, "currency", None) or "USD",
            usage_start_time=start.isoformat() if start else None,
            usage_end_time=end.isoformat(),
            raw_billing_metadata={"table": table_id, "range": time_range},
            raw={"table": table_id, "range": time_range},
            created_at=datetime.now(UTC).isoformat(),
        )
        for index, row in enumerate(rows)
    ]
    store.save_records(records)
    message = "Google billing export returned no rows for this range." if not records else f"Synced {len(records)} Google billing records."
    store.update_status("google", status="ok", message=message, tables_found=len(tables))
    return records


async def get_google_official_summary(time_range: str = "30d", settings: Settings | None = None, store: SyncStore | None = None) -> UsageReconciliationResult:
    store = store or SyncStore(settings)
    records = [record for record in store.list_records("google") if record.source == "provider_official_billing"]
    total = round(sum(record.provider_reported_cost_usd or 0 for record in records), 6)
    state = store.status().get("google", {})
    notes = []
    if state.get("status") == "waiting_for_tables":
        notes.append("Google billing export is enabled, but BigQuery tables are not available yet. Billing export can take time to appear.")
    elif not records:
        notes.append("Google billing export has no synced rows for this range.")
    return UsageReconciliationResult(
        provider="google",
        range=time_range,
        scope="account_or_project",
        safety_estimated_cost_usd=0,
        provider_reported_cost_usd=total if records else None,
        status="provider_reported" if records else "unavailable",
        last_synced_at=store.last_synced_at("google"),
        notes=notes,
    )


def _google_configured(settings: Settings) -> bool:
    return bool(settings.google_application_credentials and settings.google_cloud_project_id and settings.google_billing_bigquery_dataset)


def _pick_billing_table(tables: list[str]) -> str:
    detailed = [table for table in tables if table.startswith("gcp_billing_export_resource_v1")]
    standard = [table for table in tables if table.startswith("gcp_billing_export_v1")]
    return (detailed or standard or tables)[0]


def _float(value: Any) -> float | None:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None
