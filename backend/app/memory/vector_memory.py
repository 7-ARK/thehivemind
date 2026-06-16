import json
from pathlib import Path

from app.core.config import get_settings
from app.core.models import MemorySnippet


class LocalVectorMemory:
    """Simple text-chunk store with lexical scoring.

    This deliberately mimics a vector-store interface so pgvector, Chroma, or
    another embedding-backed store can replace it later without changing agents.
    """

    def __init__(self, store_path: str | None = None) -> None:
        settings = get_settings()
        self.store_dir = Path(store_path) if store_path else settings.vector_path
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.store_file = self.store_dir / "chunks.json"
        if not self.store_file.exists():
            self.store_file.write_text("[]", encoding="utf-8")

    def add_chunk(self, title: str, content: str) -> None:
        chunks = self._read_chunks()
        chunks.append({"title": title, "content": content})
        self.store_file.write_text(json.dumps(chunks, indent=2), encoding="utf-8")

    def search(self, query: str, limit: int = 3) -> list[MemorySnippet]:
        chunks = self._read_chunks()
        if not chunks:
            self.add_chunk(
                "MVP design principle",
                "Keep TheHiveMind transparent: show agent actions, routing choices, memory retrieval, and cost estimates.",
            )
            self.add_chunk(
                "Recruiter demo angle",
                "The product should make orchestration legible with timelines, agent cards, and final artifacts.",
            )
            chunks = self._read_chunks()

        query_terms = {term.lower().strip(".,:;!?") for term in query.split() if len(term) > 2}
        scored = []
        for chunk in chunks:
            content_terms = set(chunk["content"].lower().split()) | set(chunk["title"].lower().split())
            overlap = len(query_terms & content_terms)
            score = round(min(1.0, 0.35 + overlap / 10), 2)
            scored.append(MemorySnippet(title=chunk["title"], content=chunk["content"], relevance_score=score))
        return sorted(scored, key=lambda item: item.relevance_score, reverse=True)[:limit]

    def _read_chunks(self) -> list[dict[str, str]]:
        return json.loads(self.store_file.read_text(encoding="utf-8"))
