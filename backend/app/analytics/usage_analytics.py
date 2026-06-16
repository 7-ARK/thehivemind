from __future__ import annotations

import csv
import io
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable

from fastapi import HTTPException

from app.core.config import Settings, get_settings
from app.core.cost_estimator import estimate_cost
from app.core.model_registry import get_model_metadata
from app.storage.usage_store import UsageStore

SUPPORTED_RANGES = {"today", "7d", "30d", "month", "all"}
SUPPORTED_BUCKETS = {"hour", "day", "week"}


class UsageAnalytics:
    def __init__(self, store: UsageStore | None = None, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = store or UsageStore(self.settings)

    def get_usage_summary(self, time_range: str = "30d") -> dict[str, Any]:
        rows = self._rows(time_range)
        total_calls = len(rows)
        successful_calls = sum(1 for row in rows if self._success(row))
        failed_calls = total_calls - successful_calls
        total_input = sum(self._int(row, "input_tokens") for row in rows)
        total_output = sum(self._int(row, "output_tokens") for row in rows)
        total_cached = sum(self._int(row, "cached_tokens") for row in rows)
        total_reasoning = sum(self._int(row, "reasoning_tokens") for row in rows)
        estimated_cost = sum(self._float(row, "estimated_cost_usd") for row in rows)
        actual_cost = sum(self._float(row, "actual_cost_usd") for row in rows if self._value(row, "actual_cost_usd") is not None)
        effective_cost = sum(self._effective_cost(row) for row in rows)
        latencies = [self._int(row, "latency_ms") for row in rows]
        budget = self.get_budget_status(time_range)

        return {
            "range": time_range,
            "total_calls": total_calls,
            "successful_calls": successful_calls,
            "failed_calls": failed_calls,
            "success_rate": self._percent(successful_calls, total_calls),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cached_tokens": total_cached,
            "total_reasoning_tokens": total_reasoning,
            "total_tokens": total_input + total_output + total_reasoning,
            "estimated_cost_usd": round(estimated_cost, 6),
            "total_estimated_cost_usd": round(estimated_cost, 6),
            "actual_cost_usd": round(actual_cost, 6),
            "effective_cost_usd": round(effective_cost, 6),
            "cached_token_savings_usd": self.get_cached_token_savings(time_range)["estimated_savings_usd"],
            "search_calls": sum(self._int(row, "search_calls") for row in rows),
            "search_cost_usd": round(sum(self._float(row, "search_cost_usd") for row in rows), 6),
            "average_latency_ms": self._average(latencies),
            "p95_latency_ms": self._p95(latencies),
            "most_used_provider": self._top_count(rows, "provider"),
            "most_used_model": self._top_count(rows, "model"),
            "most_expensive_model": self._top_cost(rows, "model"),
            "most_expensive_agent": self._top_cost(rows, "agent_name"),
            "budget_status": budget,
            # Backward-compatible fields from the previous summary endpoint.
            "calls_by_provider": self._count_by(rows, "provider"),
            "cost_by_provider": self._cost_by(rows, "provider"),
            "cost_by_model": self._cost_by(rows, "model"),
            "cost_by_agent": self._cost_by(rows, "agent_name"),
            "recent_calls": self.get_recent_calls(10)["recent_calls"],
        }

    def get_cost_by_provider(self, time_range: str = "30d") -> dict[str, Any]:
        rows = self._rows(time_range)
        providers = []
        for provider, group in self._group(rows, "provider").items():
            calls = len(group)
            providers.append(
                {
                    "provider": provider,
                    "calls": calls,
                    "success_rate": self._percent(sum(1 for row in group if self._success(row)), calls),
                    "input_tokens": sum(self._int(row, "input_tokens") for row in group),
                    "output_tokens": sum(self._int(row, "output_tokens") for row in group),
                    "cached_tokens": sum(self._int(row, "cached_tokens") for row in group),
                    "cost_usd": round(sum(self._effective_cost(row) for row in group), 6),
                    "avg_latency_ms": self._average([self._int(row, "latency_ms") for row in group]),
                    "failed_calls": sum(1 for row in group if not self._success(row)),
                }
            )
        return {"range": time_range, "providers": sorted(providers, key=lambda item: item["cost_usd"], reverse=True)}

    def get_cost_by_model(self, time_range: str = "30d") -> dict[str, Any]:
        rows = self._rows(time_range)
        models = []
        for model, group in self._group(rows, "model").items():
            calls = len(group)
            metadata = get_model_metadata(model)
            cost = sum(self._effective_cost(row) for row in group)
            models.append(
                {
                    "model": model,
                    "provider": self._value(group[0], "provider") or metadata.provider,
                    "role": metadata.role,
                    "calls": calls,
                    "input_tokens": sum(self._int(row, "input_tokens") for row in group),
                    "output_tokens": sum(self._int(row, "output_tokens") for row in group),
                    "cost_usd": round(cost, 6),
                    "avg_cost_per_call": round(cost / calls, 6) if calls else 0,
                    "avg_latency_ms": self._average([self._int(row, "latency_ms") for row in group]),
                    "success_rate": self._percent(sum(1 for row in group if self._success(row)), calls),
                }
            )
        return {"range": time_range, "models": sorted(models, key=lambda item: item["cost_usd"], reverse=True)}

    def get_cost_by_agent(self, time_range: str = "30d") -> dict[str, Any]:
        rows = self._rows(time_range)
        agents = []
        for agent_name, group in self._group(rows, "agent_name").items():
            calls = len(group)
            agents.append(
                {
                    "agent_name": agent_name,
                    "agent_role": self._value(group[0], "agent_role") or "unassigned",
                    "model": self._value(group[0], "model"),
                    "provider": self._value(group[0], "provider"),
                    "calls": calls,
                    "cost_usd": round(sum(self._effective_cost(row) for row in group), 6),
                    "tokens": sum(self._int(row, "input_tokens") + self._int(row, "output_tokens") for row in group),
                    "avg_latency_ms": self._average([self._int(row, "latency_ms") for row in group]),
                    "success_rate": self._percent(sum(1 for row in group if self._success(row)), calls),
                }
            )
        return {"range": time_range, "agents": sorted(agents, key=lambda item: item["cost_usd"], reverse=True)}

    def get_token_usage_by_model(self, time_range: str = "30d") -> dict[str, Any]:
        rows = self._rows(time_range)
        models = []
        for model, group in self._group(rows, "model").items():
            models.append(
                {
                    "model": model,
                    "provider": self._value(group[0], "provider"),
                    "input_tokens": sum(self._int(row, "input_tokens") for row in group),
                    "output_tokens": sum(self._int(row, "output_tokens") for row in group),
                    "cached_tokens": sum(self._int(row, "cached_tokens") for row in group),
                    "reasoning_tokens": sum(self._int(row, "reasoning_tokens") for row in group),
                    "total_tokens": sum(
                        self._int(row, "input_tokens") + self._int(row, "output_tokens") + self._int(row, "reasoning_tokens")
                        for row in group
                    ),
                }
            )
        return {"range": time_range, "models": sorted(models, key=lambda item: item["total_tokens"], reverse=True)}

    def get_latency_stats(self, time_range: str = "30d") -> dict[str, Any]:
        rows = self._rows(time_range)
        latencies = [self._int(row, "latency_ms") for row in rows]
        return {
            "range": time_range,
            "average_latency_ms": self._average(latencies),
            "p95_latency_ms": self._p95(latencies),
            "max_latency_ms": max(latencies) if latencies else 0,
            "by_provider": [
                {
                    "provider": provider,
                    "avg_latency_ms": self._average([self._int(row, "latency_ms") for row in group]),
                    "p95_latency_ms": self._p95([self._int(row, "latency_ms") for row in group]),
                }
                for provider, group in self._group(rows, "provider").items()
            ],
        }

    def get_failure_stats(self, time_range: str = "30d") -> dict[str, Any]:
        rows = self._rows(time_range)
        failed = [row for row in rows if not self._success(row)]
        return {
            "range": time_range,
            "failed_calls": len(failed),
            "failure_rate": self._percent(len(failed), len(rows)),
            "failures_by_provider": self._count_by(failed, "provider"),
            "failures_by_model": self._count_by(failed, "model"),
            "recent_failures": [self._recent_call(row) for row in failed[:10]],
        }

    def get_recent_calls(self, limit: int = 20) -> dict[str, Any]:
        rows = self.store.rows()[: max(1, min(limit, 100))]
        return {"recent_calls": [self._recent_call(row) for row in rows]}

    def get_expensive_runs(self, limit: int = 10) -> dict[str, Any]:
        rows = [row for row in self.store.rows() if self._value(row, "run_id")]
        run_titles = self._run_titles()
        runs = []
        for run_id, group in self._group(rows, "run_id").items():
            runs.append(
                {
                    "run_id": run_id,
                    "title": run_titles.get(run_id, f"Run {run_id}"),
                    "total_cost_usd": round(sum(self._effective_cost(row) for row in group), 6),
                    "total_tokens": sum(self._int(row, "input_tokens") + self._int(row, "output_tokens") for row in group),
                    "providers_used": sorted({self._value(row, "provider") for row in group if self._value(row, "provider")}),
                    "models_used": sorted({self._value(row, "model") for row in group if self._value(row, "model")}),
                    "agents_used": sorted({self._value(row, "agent_name") for row in group if self._value(row, "agent_name")}),
                    "call_count": len(group),
                    "failed_calls": sum(1 for row in group if not self._success(row)),
                    "run_timestamp": min(self._value(row, "created_at") for row in group),
                }
            )
        return {"runs": sorted(runs, key=lambda item: item["total_cost_usd"], reverse=True)[: max(1, min(limit, 100))]}

    def _run_titles(self) -> dict[str, str]:
        try:
            with sqlite3.connect(self.store.db_path) as conn:
                rows = conn.execute("SELECT run_id, command FROM runs").fetchall()
        except sqlite3.Error:
            return {}
        return {run_id: command for run_id, command in rows}

    def get_budget_status(self, time_range: str = "30d") -> dict[str, Any]:
        rows = self._rows(time_range)
        spent = round(sum(self._effective_cost(row) for row in rows), 6)
        budget = self.settings.daily_ai_budget_usd if time_range == "today" else self.settings.monthly_ai_budget_usd
        percent = round((spent / budget) * 100, 2) if budget else 0
        if percent >= 100:
            status = "exceeded"
        elif percent >= self.settings.danger_budget_percent:
            status = "danger"
        elif percent >= self.settings.warning_budget_percent:
            status = "warning"
        else:
            status = "safe"
        return {
            "monthly_budget_usd": self.settings.monthly_ai_budget_usd,
            "daily_budget_usd": self.settings.daily_ai_budget_usd,
            "spent_usd": spent,
            "remaining_usd": round(max(0.0, budget - spent), 6),
            "percent_used": percent,
            "status": status,
        }

    def get_cached_token_savings(self, time_range: str = "30d") -> dict[str, Any]:
        rows = self._rows(time_range)
        total_cached = sum(self._int(row, "cached_tokens") for row in rows)
        normal_cost = 0.0
        cached_cost = 0.0
        by_model: dict[str, dict[str, Any]] = {}
        for row in rows:
            cached_tokens = self._int(row, "cached_tokens")
            if not cached_tokens:
                continue
            model = self._value(row, "model")
            provider = self._value(row, "provider")
            normal = estimate_cost(model, cached_tokens, 0, 0).estimated_cost_usd
            actual = estimate_cost(model, cached_tokens, 0, cached_tokens).estimated_cost_usd
            normal_cost += normal
            cached_cost += actual
            key = f"{provider}:{model}"
            entry = by_model.setdefault(
                key,
                {"provider": provider, "model": model, "cached_tokens": 0, "normal_input_cost_usd": 0, "actual_cached_cost_usd": 0, "estimated_savings_usd": 0},
            )
            entry["cached_tokens"] += cached_tokens
            entry["normal_input_cost_usd"] = round(entry["normal_input_cost_usd"] + normal, 6)
            entry["actual_cached_cost_usd"] = round(entry["actual_cached_cost_usd"] + actual, 6)
            entry["estimated_savings_usd"] = round(entry["normal_input_cost_usd"] - entry["actual_cached_cost_usd"], 6)
        return {
            "range": time_range,
            "cached_tokens": total_cached,
            "normal_input_cost_usd": round(normal_cost, 6),
            "actual_cached_cost_usd": round(cached_cost, 6),
            "estimated_savings_usd": round(max(0.0, normal_cost - cached_cost), 6),
            "savings_by_model_provider": list(by_model.values()),
        }

    def get_search_usage(self, time_range: str = "30d") -> dict[str, Any]:
        rows = self._rows(time_range)
        total_calls = sum(self._int(row, "search_calls") for row in rows)
        return {
            "range": time_range,
            "total_search_calls": total_calls,
            "search_cost_usd": round(sum(self._float(row, "search_cost_usd") for row in rows), 6),
            "search_by_provider": self._sum_field(rows, "provider", "search_calls"),
            "search_by_agent": self._sum_field(rows, "agent_name", "search_calls"),
            "estimated_cost_usd": round(sum(self._float(row, "search_cost_usd") for row in rows), 6),
            "status": "Search and grounding are currently disabled." if total_calls == 0 else "Search usage recorded.",
        }

    def get_timeseries(self, time_range: str = "30d", bucket: str = "day") -> dict[str, Any]:
        self._validate_bucket(bucket)
        rows = self._rows(time_range)
        grouped: dict[str, list] = defaultdict(list)
        for row in rows:
            grouped[self._bucket_key(self._created_at(row), bucket)].append(row)
        points = []
        for key in sorted(grouped):
            group = grouped[key]
            calls = len(group)
            points.append(
                {
                    "date": key,
                    "calls": calls,
                    "cost_usd": round(sum(self._effective_cost(row) for row in group), 6),
                    "input_tokens": sum(self._int(row, "input_tokens") for row in group),
                    "output_tokens": sum(self._int(row, "output_tokens") for row in group),
                    "failed_calls": sum(1 for row in group if not self._success(row)),
                    "avg_latency_ms": self._average([self._int(row, "latency_ms") for row in group]),
                }
            )
        return {"range": time_range, "bucket": bucket, "points": points}

    def export_csv(self, time_range: str = "30d") -> str:
        rows = self._rows(time_range)
        output = io.StringIO()
        fieldnames = [
            "created_at",
            "run_id",
            "agent_name",
            "provider",
            "model",
            "mode",
            "input_tokens",
            "output_tokens",
            "cached_tokens",
            "total_cost_usd",
            "latency_ms",
            "success",
            "request_type",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: self._csv_value(row, field) for field in fieldnames})
        return output.getvalue()

    def _rows(self, time_range: str) -> list:
        self._validate_range(time_range)
        rows = self.store.rows()
        start = self._range_start(time_range)
        if start is None:
            return rows
        return [row for row in rows if self._created_at(row) >= start]

    def _validate_range(self, time_range: str) -> None:
        if time_range not in SUPPORTED_RANGES:
            raise HTTPException(status_code=400, detail=f"Unsupported range. Use one of: {', '.join(sorted(SUPPORTED_RANGES))}.")

    def _validate_bucket(self, bucket: str) -> None:
        if bucket not in SUPPORTED_BUCKETS:
            raise HTTPException(status_code=400, detail=f"Unsupported bucket. Use one of: {', '.join(sorted(SUPPORTED_BUCKETS))}.")

    def _range_start(self, time_range: str) -> datetime | None:
        now = datetime.now(UTC)
        if time_range == "all":
            return None
        if time_range == "today":
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if time_range == "7d":
            return now - timedelta(days=7)
        if time_range == "30d":
            return now - timedelta(days=30)
        if time_range == "month":
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return None

    def _created_at(self, row) -> datetime:
        value = self._value(row, "created_at")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    def _bucket_key(self, value: datetime, bucket: str) -> str:
        if bucket == "hour":
            return value.strftime("%Y-%m-%d %H:00")
        if bucket == "week":
            year, week, _ = value.isocalendar()
            return f"{year}-W{week:02d}"
        return value.strftime("%Y-%m-%d")

    def _group(self, rows: Iterable, field: str) -> dict[str, list]:
        grouped: dict[str, list] = defaultdict(list)
        for row in rows:
            grouped[str(self._value(row, field) or "unassigned")].append(row)
        return dict(grouped)

    def _count_by(self, rows: Iterable, field: str) -> dict[str, int]:
        return {key: len(group) for key, group in self._group(rows, field).items()}

    def _cost_by(self, rows: Iterable, field: str) -> dict[str, float]:
        return {key: round(sum(self._effective_cost(row) for row in group), 6) for key, group in self._group(rows, field).items()}

    def _sum_field(self, rows: Iterable, group_field: str, sum_field: str) -> dict[str, int]:
        return {key: sum(self._int(row, sum_field) for row in group) for key, group in self._group(rows, group_field).items()}

    def _top_count(self, rows: list, field: str) -> str | None:
        counts = self._count_by(rows, field)
        return max(counts, key=counts.get) if counts else None

    def _top_cost(self, rows: list, field: str) -> str | None:
        costs = self._cost_by(rows, field)
        return max(costs, key=costs.get) if costs else None

    def _recent_call(self, row) -> dict[str, Any]:
        return {
            "id": self._value(row, "id"),
            "timestamp": self._value(row, "created_at"),
            "provider": self._value(row, "provider"),
            "model": self._value(row, "model"),
            "agent": self._value(row, "agent_name"),
            "request_type": self._value(row, "request_type"),
            "success": self._success(row),
            "input_tokens": self._int(row, "input_tokens"),
            "output_tokens": self._int(row, "output_tokens"),
            "cost_usd": round(self._effective_cost(row), 6),
            "latency_ms": self._int(row, "latency_ms"),
            "error_message": self._short_error(row),
            "metadata": self._safe_metadata(row),
        }

    def _safe_metadata(self, row) -> dict[str, Any]:
        raw = self._value(row, "metadata_json") or "{}"
        try:
            metadata = __import__("json").loads(raw)
        except Exception:
            return {}
        allowed = {"effective_provider", "usage_source", "mock", "response_id"}
        return {key: value for key, value in metadata.items() if key in allowed}

    def _short_error(self, row) -> str | None:
        error = self._value(row, "error_message")
        return error[:180] if error else None

    def _effective_cost(self, row) -> float:
        actual = self._value(row, "actual_cost_usd")
        if actual is not None:
            return float(actual)
        total = self._value(row, "total_cost_usd")
        return float(total if total is not None else self._value(row, "estimated_cost_usd") or 0)

    def _success(self, row) -> bool:
        return bool(self._int(row, "success"))

    def _int(self, row, field: str) -> int:
        value = self._value(row, field)
        return int(value or 0)

    def _float(self, row, field: str) -> float:
        value = self._value(row, field)
        return float(value or 0)

    def _value(self, row, field: str) -> Any:
        return row[field] if field in row.keys() else None

    def _average(self, values: list[int]) -> float:
        return round(sum(values) / len(values), 2) if values else 0

    def _p95(self, values: list[int]) -> float:
        if not values:
            return 0
        ordered = sorted(values)
        index = min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95)))
        return ordered[index]

    def _percent(self, numerator: int | float, denominator: int | float) -> float:
        return round((numerator / denominator) * 100, 2) if denominator else 0

    def _csv_value(self, row, field: str) -> Any:
        if field == "total_cost_usd":
            return round(self._effective_cost(row), 6)
        if field == "success":
            return self._success(row)
        return self._value(row, field)


def get_usage_summary(time_range: str = "30d") -> dict[str, Any]:
    return UsageAnalytics().get_usage_summary(time_range)


def get_cost_by_provider(time_range: str = "30d") -> dict[str, Any]:
    return UsageAnalytics().get_cost_by_provider(time_range)


def get_cost_by_model(time_range: str = "30d") -> dict[str, Any]:
    return UsageAnalytics().get_cost_by_model(time_range)


def get_cost_by_agent(time_range: str = "30d") -> dict[str, Any]:
    return UsageAnalytics().get_cost_by_agent(time_range)


def get_token_usage_by_model(time_range: str = "30d") -> dict[str, Any]:
    return UsageAnalytics().get_token_usage_by_model(time_range)


def get_latency_stats(time_range: str = "30d") -> dict[str, Any]:
    return UsageAnalytics().get_latency_stats(time_range)


def get_failure_stats(time_range: str = "30d") -> dict[str, Any]:
    return UsageAnalytics().get_failure_stats(time_range)


def get_recent_calls(limit: int = 20) -> dict[str, Any]:
    return UsageAnalytics().get_recent_calls(limit)


def get_expensive_runs(limit: int = 10) -> dict[str, Any]:
    return UsageAnalytics().get_expensive_runs(limit)


def get_budget_status(time_range: str = "30d") -> dict[str, Any]:
    return UsageAnalytics().get_budget_status(time_range)


def get_cached_token_savings(time_range: str = "30d") -> dict[str, Any]:
    return UsageAnalytics().get_cached_token_savings(time_range)


def get_search_usage(time_range: str = "30d") -> dict[str, Any]:
    return UsageAnalytics().get_search_usage(time_range)
