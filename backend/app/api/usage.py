from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query, Response

from app.analytics.usage_analytics import UsageAnalytics
from app.core.config import get_settings
from app.storage.usage_store import UsageStore
from app.usage_sync.real_usage_service import RealUsageService


router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("/real/summary")
def real_usage_summary(include_dev_estimates: bool = Query(False)) -> dict:
    return RealUsageService().summary(include_dev_estimates)


@router.get("/real/runs")
def real_usage_runs(include_dev_estimates: bool = Query(False)) -> dict:
    return RealUsageService().runs(include_dev_estimates)


@router.get("/real/models")
def real_usage_models(include_dev_estimates: bool = Query(False)) -> dict:
    return RealUsageService().models(include_dev_estimates)


@router.get("/real/providers")
def real_usage_providers(include_dev_estimates: bool = Query(False)) -> dict:
    return RealUsageService().providers(include_dev_estimates)


@router.get("/real/openrouter-breakdown")
def real_usage_openrouter_breakdown() -> dict:
    return RealUsageService().openrouter_breakdown()


@router.get("/real/provider-responses")
def real_usage_provider_responses(include_dev_estimates: bool = Query(False), limit: int = Query(100, ge=1, le=500)) -> dict:
    return {"records": RealUsageService().provider_responses(include_dev_estimates, limit)}


@router.get("/official/account-billing")
def official_account_billing() -> dict:
    return RealUsageService().account_billing()


@router.get("/summary")
def usage_summary(time_range: str = Query("30d", alias="range")) -> dict:
    return UsageAnalytics().get_usage_summary(time_range)


@router.get("/providers")
def usage_providers(time_range: str = Query("30d", alias="range")) -> dict:
    return UsageAnalytics().get_cost_by_provider(time_range)


@router.get("/models")
def usage_models(time_range: str = Query("30d", alias="range")) -> dict:
    return UsageAnalytics().get_cost_by_model(time_range)


@router.get("/agents")
def usage_agents(time_range: str = Query("30d", alias="range")) -> dict:
    return UsageAnalytics().get_cost_by_agent(time_range)


@router.get("/tokens")
def usage_tokens(time_range: str = Query("30d", alias="range")) -> dict:
    return UsageAnalytics().get_token_usage_by_model(time_range)


@router.get("/latency")
def usage_latency(time_range: str = Query("30d", alias="range")) -> dict:
    return UsageAnalytics().get_latency_stats(time_range)


@router.get("/failures")
def usage_failures(time_range: str = Query("30d", alias="range")) -> dict:
    return UsageAnalytics().get_failure_stats(time_range)


@router.get("/recent")
def usage_recent(limit: int = Query(20, ge=1, le=100)) -> dict:
    return UsageAnalytics().get_recent_calls(limit)


@router.get("/expensive-runs")
def usage_expensive_runs(limit: int = Query(10, ge=1, le=100)) -> dict:
    return UsageAnalytics().get_expensive_runs(limit)


@router.get("/budget")
def usage_budget(time_range: str = Query("30d", alias="range")) -> dict:
    return UsageAnalytics().get_budget_status(time_range)


@router.get("/search")
def usage_search(time_range: str = Query("30d", alias="range")) -> dict:
    return UsageAnalytics().get_search_usage(time_range)


@router.get("/cache")
def usage_cache(time_range: str = Query("30d", alias="range")) -> dict:
    return UsageAnalytics().get_cached_token_savings(time_range)


@router.get("/timeseries")
def usage_timeseries(time_range: str = Query("30d", alias="range"), bucket: str = Query("day")) -> dict:
    return UsageAnalytics().get_timeseries(time_range, bucket)


@router.get("/export.csv")
def usage_export_csv(time_range: str = Query("30d", alias="range")) -> Response:
    csv_body = UsageAnalytics().export_csv(time_range)
    return Response(
        content=csv_body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="thehivemind-usage-{time_range}.csv"'},
    )


@router.post("/seed-demo")
def seed_demo_usage() -> dict:
    settings = get_settings()
    if settings.app_env != "development":
        raise HTTPException(status_code=403, detail="Demo usage seeding is only enabled when APP_ENV=development.")

    store = UsageStore(settings)
    now = datetime.now(UTC)
    rows = [
        {
            "run_id": "demo-run-001",
            "task_id": "demo-task-ceo",
            "agent_name": "CEO Agent",
            "agent_role": "planner",
            "provider": "openai",
            "model": "gpt-5.5",
            "mode": "mock",
            "request_type": "demo_seed",
            "input_tokens": 1800,
            "output_tokens": 420,
            "cached_tokens": 300,
            "reasoning_tokens": 80,
            "estimated_cost_usd": 0.0156,
            "latency_ms": 950,
            "success": True,
            "created_at": now - timedelta(hours=18),
        },
        {
            "run_id": "demo-run-001",
            "task_id": "demo-task-selector",
            "agent_name": "Model Selector Agent",
            "agent_role": "router",
            "provider": "gemini",
            "model": "gemini-3.5-flash",
            "mode": "mock",
            "request_type": "demo_seed",
            "input_tokens": 780,
            "output_tokens": 160,
            "cached_tokens": 0,
            "estimated_cost_usd": 0.00261,
            "latency_ms": 410,
            "success": True,
            "created_at": now - timedelta(hours=17, minutes=58),
        },
        {
            "run_id": "demo-run-001",
            "task_id": "demo-task-research",
            "agent_name": "Research Agent",
            "agent_role": "search_worker",
            "provider": "gemini",
            "model": "gemini-3.1-flash-lite",
            "mode": "mock",
            "request_type": "demo_seed",
            "input_tokens": 1400,
            "output_tokens": 260,
            "cached_tokens": 150,
            "search_calls": 0,
            "search_cost_usd": 0,
            "estimated_cost_usd": 0.00074,
            "latency_ms": 530,
            "success": True,
            "created_at": now - timedelta(days=2),
        },
        {
            "run_id": "demo-run-002",
            "task_id": "demo-task-coding",
            "agent_name": "Coding Agent",
            "agent_role": "technical_worker",
            "provider": "openai",
            "model": "gpt-5.4-nano",
            "mode": "mock",
            "request_type": "demo_seed",
            "input_tokens": 2200,
            "output_tokens": 520,
            "cached_tokens": 500,
            "estimated_cost_usd": 0.00099,
            "latency_ms": 730,
            "success": True,
            "created_at": now - timedelta(days=4),
        },
        {
            "run_id": "demo-run-002",
            "task_id": "demo-task-content",
            "agent_name": "Content Agent",
            "agent_role": "content_worker",
            "provider": "openrouter",
            "model": settings.openrouter_default_model,
            "mode": "mock",
            "request_type": "demo_seed",
            "input_tokens": 1100,
            "output_tokens": 380,
            "cached_tokens": 0,
            "estimated_cost_usd": 0.000262,
            "actual_cost_usd": 0.00025,
            "latency_ms": 620,
            "success": True,
            "created_at": now - timedelta(days=9),
        },
        {
            "run_id": "demo-run-003",
            "task_id": "demo-task-qa",
            "agent_name": "QA Agent",
            "agent_role": "reviewer",
            "provider": "openai",
            "model": "gpt-5.4-nano",
            "mode": "mock",
            "request_type": "demo_seed",
            "input_tokens": 900,
            "output_tokens": 180,
            "cached_tokens": 0,
            "estimated_cost_usd": 0.000405,
            "latency_ms": 470,
            "success": False,
            "error_message": "Demo transient provider timeout",
            "created_at": now - timedelta(days=14),
        },
    ]
    ids = []
    for row in rows:
        ids.append(store.log_call(**row, metadata={"demo": True}))
    return {"inserted": len(ids), "usage_log_ids": ids}
