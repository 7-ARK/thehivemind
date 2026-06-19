from __future__ import annotations

from app.search_tools.schemas import SearchRequest, SearchResultPayload
from app.search_tools.source_formatter import mock_sources


async def run_gemini_google_search(request: SearchRequest) -> SearchResultPayload:
    if request.mode != "live":
        return SearchResultPayload(
            research_used=True,
            search_provider_id="gemini_google_search",
            query_plan=[request.query],
            sources=mock_sources(request.query, "gemini_google_search", request.max_results),
            brief="Mock Gemini Google Search result. No paid API call was made.",
            limitations=["Mock mode uses placeholder sources.", "Google billing export can be delayed for live runs."],
            cost={"source": "mock", "estimated_usd": 0.0},
        )
    raise RuntimeError("Live Gemini Google Search is gated and not executed by tests.")
