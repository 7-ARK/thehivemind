from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.memory.memory_index import content_hash, keywords, normalize_text, sparse_vector
from app.memory.memory_policies import redact_secrets, token_estimate
from app.memory.schemas import MemoryItem


class MemoryStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = self.settings.memory_path
        self.root.mkdir(parents=True, exist_ok=True)
        self._ensure_core_seed()

    def add_item(self, payload: dict[str, Any]) -> MemoryItem:
        now = datetime.now(UTC).isoformat()
        text = "\n".join(str(payload.get(key) or "") for key in ("title", "summary", "content"))
        redacted_text, sensitive = redact_secrets(text)
        title, summary, content = _split_redacted(payload, redacted_text)
        item = MemoryItem(
            id=str(payload.get("id") or uuid.uuid4()),
            project_id=payload.get("project_id"),
            scope=payload.get("scope") or ("project" if payload.get("project_id") else "global"),
            memory_type=payload["memory_type"],
            title=title,
            content=content,
            summary=summary,
            source_type=payload.get("source_type", "manual"),
            source_path=payload.get("source_path"),
            source_run_id=payload.get("source_run_id"),
            source_artifact_id=payload.get("source_artifact_id"),
            created_at=payload.get("created_at") or now,
            updated_at=now,
            tags=list(dict.fromkeys(payload.get("tags", []))),
            importance=payload.get("importance", 3),
            recency_score=payload.get("recency_score", 1.0),
            trust_score=payload.get("trust_score", 0.8),
            expires_at=payload.get("expires_at"),
            is_active=payload.get("is_active", True),
            is_sensitive=bool(payload.get("is_sensitive", False) or sensitive),
            should_inject_by_default=payload.get("should_inject_by_default", True),
            allowed_agents=payload.get("allowed_agents", []),
            blocked_agents=payload.get("blocked_agents", []),
            token_estimate=token_estimate(redacted_text),
            sparse_vector=sparse_vector(redacted_text),
            keywords=keywords(redacted_text),
            normalized_text=normalize_text(redacted_text),
            hash=content_hash(redacted_text),
            constraints=payload.get("constraints", []),
            models_used=payload.get("models_used", []),
            agents_used=payload.get("agents_used", []),
            search_provider=payload.get("search_provider"),
            source_urls=payload.get("source_urls", []),
            file_paths=payload.get("file_paths", []),
            error_types=payload.get("error_types", []),
            metadata=payload.get("metadata", {}),
        )
        self._append(item)
        self.rebuild_index(item.project_id)
        return item

    def items(self, project_id: str | None = None, memory_type: str | None = None, include_global: bool = True) -> list[MemoryItem]:
        records: list[MemoryItem] = []
        if include_global:
            records.extend(self._read_path(self._global_items_path()))
        if project_id:
            records.extend(self._read_path(self._project_items_path(project_id)))
        elif not include_global:
            for path in (self.root / "projects").glob("*/memory_items.jsonl"):
                records.extend(self._read_path(path))
        if memory_type:
            records = [item for item in records if item.memory_type == memory_type]
        return [item for item in records if item.is_active]

    def rebuild_index(self, project_id: str | None = None) -> dict[str, Any]:
        if project_id:
            items = self.items(project_id=project_id, include_global=False)
            index_path = self._project_index_path(project_id)
        else:
            items = self.items(project_id=None, include_global=True)
            index_path = self.root / "global" / "vector_index.json"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index = {
            "updated_at": datetime.now(UTC).isoformat(),
            "item_count": len(items),
            "vectors": [{"id": item.id, "hash": item.hash, "sparse_vector": item.sparse_vector} for item in items],
        }
        index_path.write_text(json.dumps(index, indent=2, ensure_ascii=True), encoding="utf-8")
        if project_id:
            self._write_manifest(project_id, items)
        return index

    def status(self) -> dict[str, Any]:
        project_counts = []
        project_root = self.root / "projects"
        if project_root.exists():
            for folder in sorted(path for path in project_root.iterdir() if path.is_dir()):
                items = self.items(project_id=folder.name, include_global=False)
                manifest = self._read_json(folder / "memory_manifest.json", {})
                project_counts.append(
                    {
                        "project_id": folder.name,
                        "memory_count": len(items),
                        "last_indexed_at": manifest.get("last_indexed_at"),
                        "types": dict(Counter(item.memory_type for item in items)),
                    }
                )
        global_items = self.items(project_id=None, include_global=True)
        return {
            "enabled": self.settings.enable_vector_memory,
            "backend_mode": "local_sparse",
            "total_memory_items": len(global_items) + sum(item["memory_count"] for item in project_counts),
            "global_memory_items": len(global_items),
            "projects": project_counts,
            "index_status": "ready",
            "last_updated_at": max((item.updated_at for item in global_items), default=None),
            "no_secrets": True,
        }

    def _append(self, item: MemoryItem) -> None:
        path = self._global_items_path() if item.scope == "global" else self._project_items_path(item.project_id or "unassigned")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(item.model_dump_json() + "\n")

    def _read_path(self, path: Path) -> list[MemoryItem]:
        if not path.exists():
            return []
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(MemoryItem.model_validate_json(line))
            except Exception:
                continue
        return records

    def _global_items_path(self) -> Path:
        return self.root / "global" / "memory_items.jsonl"

    def _project_items_path(self, project_id: str) -> Path:
        return self.root / "projects" / project_id / "memory_items.jsonl"

    def _project_index_path(self, project_id: str) -> Path:
        return self.root / "projects" / project_id / "vector_index.json"

    def _write_manifest(self, project_id: str, items: list[MemoryItem]) -> None:
        path = self.root / "projects" / project_id / "memory_manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        manifest = {
            "project_id": project_id,
            "memory_count": len(items),
            "last_indexed_at": datetime.now(UTC).isoformat(),
            "types": dict(Counter(item.memory_type for item in items)),
        }
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")

    def _ensure_core_seed(self) -> None:
        seed_path = self.root / "core_memory.json"
        if not seed_path.exists():
            source = Path(__file__).resolve().parents[3] / "backend" / "data" / "memory" / "core_memory.json"
            seed_path.parent.mkdir(parents=True, exist_ok=True)
            seed_path.write_text(source.read_text(encoding="utf-8") if source.exists() else "[]", encoding="utf-8")
        if self._global_items_path().exists():
            return
        try:
            seeds = json.loads(seed_path.read_text(encoding="utf-8"))
        except Exception:
            seeds = []
        for seed in seeds:
            self.add_item(
                {
                    "scope": "global",
                    "memory_type": "core_rule",
                    "title": seed.get("title", "Core memory"),
                    "summary": seed.get("content", "")[:240],
                    "content": seed.get("content", ""),
                    "source_type": "manual",
                    "tags": ["core", "guardrails"],
                    "importance": 5,
                    "trust_score": 1.0,
                    "allowed_agents": [],
                }
            )

    def _read_json(self, path: Path, fallback: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return fallback


def _split_redacted(payload: dict[str, Any], redacted_text: str) -> tuple[str, str, str]:
    original = "\n".join(str(payload.get(key) or "") for key in ("title", "summary", "content"))
    if original == redacted_text:
        return str(payload.get("title") or ""), str(payload.get("summary") or ""), str(payload.get("content") or "")
    return (
        redact_secrets(str(payload.get("title") or ""))[0],
        redact_secrets(str(payload.get("summary") or ""))[0],
        redact_secrets(str(payload.get("content") or ""))[0],
    )
