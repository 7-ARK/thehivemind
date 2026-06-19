from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlparse

from app.search_tools.schemas import SearchSource


def mock_sources(query: str, provider_id: str, max_results: int) -> list[SearchSource]:
    retrieved_at = datetime.now(UTC).isoformat()
    safe_count = max(1, min(max_results, 5))
    return [
        SearchSource(
            title=f"Mock source {index + 1} for {query[:60]}",
            url=f"https://example.com/{provider_id}/source-{index + 1}",
            domain="example.com",
            retrieved_at=retrieved_at,
            snippet="Mock-mode source placeholder. No live provider search or paid API call was made.",
        )
        for index in range(safe_count)
    ]


def source_from_url(title: str, url: str, snippet: str = "") -> SearchSource:
    return SearchSource(
        title=title or url,
        url=url,
        domain=urlparse(url).netloc or None,
        retrieved_at=datetime.now(UTC).isoformat(),
        snippet=snippet,
    )
