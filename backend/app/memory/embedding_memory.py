import json
import math
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings


class EmbeddingMemory:
    """Provider-independent memory interface with deterministic local scoring.

    This is intentionally API-free for v1. It preserves metadata and retrieval
    discipline now, while leaving room for real embeddings later.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.path = self.settings.vector_path / "memories.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def add_memory(self, text: str, metadata: dict[str, Any]) -> str:
        memory_id = str(uuid.uuid4())
        entries = self._read()
        entries.append(
            {
                "id": memory_id,
                "text": text,
                "metadata": {
                    **metadata,
                    "created_at": metadata.get("created_at") or datetime.now(UTC).isoformat(),
                },
            }
        )
        self.path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
        return memory_id

    def search_memory(self, query: str, top_k: int = 5, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        query_terms = self._terms(query)
        results = []
        for entry in self._read():
            metadata = entry.get("metadata", {})
            if any(metadata.get(key) != value for key, value in filters.items()):
                continue
            score = self._score(query_terms, self._terms(entry.get("text", "")))
            results.append({**entry, "score": round(score, 4)})
        return sorted(results, key=lambda item: item["score"], reverse=True)[:top_k]

    def _read(self) -> list[dict[str, Any]]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _terms(self, text: str) -> Counter[str]:
        return Counter(term.strip(".,:;!?()[]{}\"'").lower() for term in text.split() if len(term.strip()) > 2)

    def _score(self, query_terms: Counter[str], doc_terms: Counter[str]) -> float:
        if not query_terms or not doc_terms:
            return 0.0
        overlap = set(query_terms) & set(doc_terms)
        numerator = sum(query_terms[term] * doc_terms[term] for term in overlap)
        query_norm = math.sqrt(sum(count * count for count in query_terms.values()))
        doc_norm = math.sqrt(sum(count * count for count in doc_terms.values()))
        return numerator / max(1e-9, query_norm * doc_norm)


def add_memory(text: str, metadata: dict[str, Any]) -> str:
    return EmbeddingMemory().add_memory(text, metadata)


def search_memory(query: str, top_k: int = 5, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return EmbeddingMemory().search_memory(query, top_k, filters)
