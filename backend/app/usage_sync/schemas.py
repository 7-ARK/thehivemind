from typing import Any, Literal

from pydantic import BaseModel, Field


ProviderUsageSource = Literal[
    "provider_response",
    "provider_generation_lookup",
    "provider_official_billing",
    "provider_account_balance",
    "mock_dev_only",
    "safety_estimate_dev_only",
]
UsageScope = Literal["run", "account", "project", "account_or_project", "unknown"]
ReconciliationStatus = Literal["mock_only", "estimated", "provider_reported", "reconciled", "unavailable", "error"]


class ProviderUsageRecord(BaseModel):
    id: str
    provider: str
    source: ProviderUsageSource
    scope: UsageScope = "unknown"
    account_id: str | None = None
    project_id: str | None = None
    api_key_id: str | None = None
    run_id: str | None = None
    agent_name: str | None = None
    request_id: str | None = None
    response_id: str | None = None
    generation_id: str | None = None
    requested_model: str | None = None
    actual_model: str | None = None
    model: str | None = None
    openrouter_provider_name: str | None = None
    service: str | None = None
    sku: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None
    safety_estimated_cost_usd: float | None = None
    provider_reported_cost_usd: float | None = None
    currency: str = "USD"
    sync_status: str | None = None
    provider_created_at: str | None = None
    local_created_at: str | None = None
    usage_start_time: str | None = None
    usage_end_time: str | None = None
    raw_usage_metadata: dict[str, Any] = Field(default_factory=dict)
    raw_billing_metadata: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class UsageReconciliationResult(BaseModel):
    provider: str
    range: str
    scope: str = "unknown"
    safety_estimated_cost_usd: float = 0
    provider_reported_cost_usd: float | None
    status: ReconciliationStatus
    last_synced_at: str | None = None
    notes: list[str] = Field(default_factory=list)
