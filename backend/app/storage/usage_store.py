import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.core.cost_estimator import estimate_cost


class UsageStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.db_path = self.settings.sqlite_path
        self._ensure_database()

    def log_call(
        self,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        agent_name: str | None = None,
        agent_role: str | None = None,
        provider: str,
        model: str,
        mode: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        reasoning_tokens: int | None = None,
        search_calls: int = 0,
        search_cost_usd: float = 0.0,
        input_cost_usd: float | None = None,
        output_cost_usd: float | None = None,
        cached_cost_usd: float | None = None,
        total_cost_usd: float | None = None,
        estimated_cost_usd: float,
        actual_cost_usd: float | None = None,
        latency_ms: int,
        success: bool,
        error_message: str | None = None,
        request_type: str = "provider_test",
        metadata: dict[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> str:
        usage_id = str(uuid.uuid4())
        metadata_json = json.dumps(metadata or {}, ensure_ascii=True)
        cost_parts = self._cost_parts(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            estimated_cost_usd=estimated_cost_usd,
            input_cost_usd=input_cost_usd,
            output_cost_usd=output_cost_usd,
            cached_cost_usd=cached_cost_usd,
            search_cost_usd=search_cost_usd,
            total_cost_usd=total_cost_usd,
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO usage_logs (
                    id, created_at, run_id, task_id, agent_name, agent_role,
                    provider, model, mode, request_type, input_tokens, output_tokens,
                    cached_tokens, reasoning_tokens, search_calls, search_cost_usd,
                    input_cost_usd, output_cost_usd, cached_cost_usd, total_cost_usd,
                    estimated_cost_usd, actual_cost_usd, latency_ms, success,
                    error_message, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usage_id,
                    (created_at or datetime.now(UTC)).isoformat(),
                    run_id,
                    task_id,
                    agent_name,
                    agent_role,
                    provider,
                    model,
                    mode,
                    request_type,
                    input_tokens,
                    output_tokens,
                    cached_tokens,
                    reasoning_tokens,
                    search_calls,
                    search_cost_usd,
                    cost_parts["input_cost_usd"],
                    cost_parts["output_cost_usd"],
                    cost_parts["cached_cost_usd"],
                    cost_parts["total_cost_usd"],
                    estimated_cost_usd,
                    actual_cost_usd,
                    latency_ms,
                    1 if success else 0,
                    error_message,
                    metadata_json,
                ),
            )
        return usage_id

    def summary(self) -> dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM usage_logs ORDER BY created_at DESC").fetchall()
        total_cost = sum(float(row["estimated_cost_usd"]) for row in rows)
        total_input = sum(int(row["input_tokens"]) for row in rows)
        total_output = sum(int(row["output_tokens"]) for row in rows)
        failed_calls = sum(1 for row in rows if not bool(row["success"]))
        avg_latency = round(sum(int(row["latency_ms"]) for row in rows) / len(rows), 2) if rows else 0

        return {
            "total_estimated_cost_usd": round(total_cost, 6),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "calls_by_provider": self._sum_count(rows, "provider"),
            "cost_by_provider": self._sum_cost(rows, "provider"),
            "cost_by_model": self._sum_cost(rows, "model"),
            "cost_by_agent": self._sum_cost(rows, "agent_name"),
            "failed_calls": failed_calls,
            "average_latency_ms": avg_latency,
            "recent_calls": [self._serialize_row(row) for row in rows[:10]],
        }

    def _ensure_database(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_logs (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    run_id TEXT,
                    task_id TEXT,
                    agent_name TEXT,
                    agent_role TEXT,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    request_type TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    cached_tokens INTEGER NOT NULL DEFAULT 0,
                    reasoning_tokens INTEGER,
                    search_calls INTEGER NOT NULL DEFAULT 0,
                    search_cost_usd REAL NOT NULL DEFAULT 0,
                    input_cost_usd REAL NOT NULL DEFAULT 0,
                    output_cost_usd REAL NOT NULL DEFAULT 0,
                    cached_cost_usd REAL NOT NULL DEFAULT 0,
                    total_cost_usd REAL NOT NULL DEFAULT 0,
                    estimated_cost_usd REAL NOT NULL,
                    actual_cost_usd REAL,
                    latency_ms INTEGER NOT NULL,
                    success INTEGER NOT NULL,
                    error_message TEXT,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            self._migrate_columns(conn)

    def _migrate_columns(self, conn: sqlite3.Connection) -> None:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(usage_logs)").fetchall()}
        columns = {
            "task_id": "TEXT",
            "agent_role": "TEXT",
            "reasoning_tokens": "INTEGER",
            "search_calls": "INTEGER NOT NULL DEFAULT 0",
            "search_cost_usd": "REAL NOT NULL DEFAULT 0",
            "input_cost_usd": "REAL NOT NULL DEFAULT 0",
            "output_cost_usd": "REAL NOT NULL DEFAULT 0",
            "cached_cost_usd": "REAL NOT NULL DEFAULT 0",
            "total_cost_usd": "REAL NOT NULL DEFAULT 0",
            "actual_cost_usd": "REAL",
        }
        for name, definition in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE usage_logs ADD COLUMN {name} {definition}")
        conn.execute(
            """
            UPDATE usage_logs
            SET total_cost_usd = estimated_cost_usd
            WHERE total_cost_usd = 0 AND estimated_cost_usd > 0
            """
        )

    def rows(self) -> list[sqlite3.Row]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT * FROM usage_logs ORDER BY created_at DESC").fetchall()

    def _sum_count(self, rows: list[sqlite3.Row], field: str) -> dict[str, int]:
        result: dict[str, int] = {}
        for row in rows:
            key = row[field] or "unassigned"
            result[key] = result.get(key, 0) + 1
        return result

    def _sum_cost(self, rows: list[sqlite3.Row], field: str) -> dict[str, float]:
        result: dict[str, float] = {}
        for row in rows:
            key = row[field] or "unassigned"
            result[key] = round(result.get(key, 0.0) + float(row["estimated_cost_usd"]), 6)
        return result

    def _serialize_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "run_id": row["run_id"],
            "task_id": self._value(row, "task_id"),
            "agent_name": row["agent_name"],
            "agent_role": self._value(row, "agent_role"),
            "provider": row["provider"],
            "model": row["model"],
            "mode": row["mode"],
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "cached_tokens": row["cached_tokens"],
            "reasoning_tokens": self._value(row, "reasoning_tokens") or 0,
            "search_calls": self._value(row, "search_calls") or 0,
            "search_cost_usd": self._value(row, "search_cost_usd") or 0,
            "input_cost_usd": self._value(row, "input_cost_usd") or 0,
            "output_cost_usd": self._value(row, "output_cost_usd") or 0,
            "cached_cost_usd": self._value(row, "cached_cost_usd") or 0,
            "total_cost_usd": self._value(row, "total_cost_usd") or row["estimated_cost_usd"],
            "estimated_cost_usd": row["estimated_cost_usd"],
            "actual_cost_usd": self._value(row, "actual_cost_usd"),
            "latency_ms": row["latency_ms"],
            "success": bool(row["success"]),
            "error_message": row["error_message"],
            "request_type": row["request_type"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
        }

    def _value(self, row: sqlite3.Row, key: str) -> Any:
        return row[key] if key in row.keys() else None

    def _cost_parts(
        self,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int,
        estimated_cost_usd: float,
        input_cost_usd: float | None,
        output_cost_usd: float | None,
        cached_cost_usd: float | None,
        search_cost_usd: float,
        total_cost_usd: float | None,
    ) -> dict[str, float]:
        estimate = estimate_cost(model, input_tokens, output_tokens, cached_tokens)
        normal_input_estimate = estimate_cost(model, input_tokens, 0, 0)
        cached_only_estimate = estimate_cost(model, cached_tokens, 0, cached_tokens) if cached_tokens else None
        calculated_input = max(0.0, normal_input_estimate.estimated_cost_usd - (cached_only_estimate.estimated_cost_usd if cached_only_estimate else 0.0))
        calculated_cached = cached_only_estimate.estimated_cost_usd if cached_only_estimate else 0.0
        calculated_output = estimate_cost(model, 0, output_tokens, 0).estimated_cost_usd
        resolved_total = total_cost_usd
        if resolved_total is None:
            resolved_total = estimated_cost_usd + search_cost_usd
        return {
            "input_cost_usd": round(input_cost_usd if input_cost_usd is not None else calculated_input, 6),
            "output_cost_usd": round(output_cost_usd if output_cost_usd is not None else calculated_output, 6),
            "cached_cost_usd": round(cached_cost_usd if cached_cost_usd is not None else calculated_cached, 6),
            "total_cost_usd": round(resolved_total, 6),
        }
