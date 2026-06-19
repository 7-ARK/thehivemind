from fastapi import APIRouter, Query

from app.usage_sync.google_billing_sync import get_google_official_summary, sync_google_billing
from app.usage_sync.exa_usage_sync import get_exa_official_summary, sync_exa_usage
from app.usage_sync.openai_usage_sync import get_openai_official_summary, sync_openai_usage
from app.usage_sync.openrouter_usage_sync import get_openrouter_official_summary, sync_openrouter_credits
from app.usage_sync.provider_sync_service import ProviderSyncService
from app.usage_sync.reconciliation_service import get_all_provider_reconciliation
from app.usage_sync.schemas import ProviderUsageRecord, UsageReconciliationResult
from app.usage_sync.sync_store import SyncStore

router = APIRouter(prefix="/api/official-usage", tags=["official-usage"])


@router.get("/status")
async def official_usage_status() -> dict:
    return await ProviderSyncService().status()


@router.post("/sync")
async def sync_official_usage(time_range: str = Query("30d", alias="range")) -> dict:
    return await ProviderSyncService().sync_all(time_range)


@router.get("/summary")
async def official_usage_summary(time_range: str = Query("30d", alias="range")) -> dict:
    return await ProviderSyncService().summary(time_range)


@router.get("/openai", response_model=UsageReconciliationResult)
async def openai_official_usage(time_range: str = Query("30d", alias="range")) -> UsageReconciliationResult:
    await sync_openai_usage(time_range)
    return await get_openai_official_summary(time_range)


@router.get("/openrouter", response_model=UsageReconciliationResult)
async def openrouter_official_usage(time_range: str = Query("30d", alias="range")) -> UsageReconciliationResult:
    await sync_openrouter_credits()
    return await get_openrouter_official_summary(time_range)


@router.get("/google", response_model=UsageReconciliationResult)
async def google_official_usage(time_range: str = Query("30d", alias="range")) -> UsageReconciliationResult:
    await sync_google_billing(time_range)
    return await get_google_official_summary(time_range)


@router.get("/exa", response_model=UsageReconciliationResult)
async def exa_official_usage(time_range: str = Query("30d", alias="range")) -> UsageReconciliationResult:
    await sync_exa_usage(time_range)
    return await get_exa_official_summary(time_range)


@router.get("/reconciliation", response_model=list[UsageReconciliationResult])
async def official_usage_reconciliation(time_range: str = Query("30d", alias="range")) -> list[UsageReconciliationResult]:
    return await get_all_provider_reconciliation(time_range)


@router.get("/raw/{provider}", response_model=list[ProviderUsageRecord])
def official_usage_raw(provider: str, limit: int = Query(20, ge=1, le=100)) -> list[ProviderUsageRecord]:
    return SyncStore().list_records(provider=provider, limit=limit)
