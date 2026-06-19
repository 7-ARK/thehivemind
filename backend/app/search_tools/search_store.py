from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings, get_settings


class SearchLogStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = self.settings.project_path.parent / "search_tools"
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "search_logs.jsonl"

    def append(self, payload: dict[str, Any]) -> dict[str, Any]:
        record = {"created_at": datetime.now(UTC).isoformat(), **payload}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        return record

    def recent(self, limit: int = 25) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        records = []
        for line in lines[-limit:]:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return list(reversed(records))
