from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SearchProviderEntry(BaseModel):
    id: str
    display_name: str
    provider: str
    status: Literal["active", "disabled", "planned"] = "active"
    enabled: bool = True
    requires_api_key: bool = True
    env_keys_required: list[str] = Field(default_factory=list)
    configured: bool = False
    available: bool = False
    available_for_live: bool = True
    available_in_mock: bool = True
    allow_web_search_global: bool = False
    live_search_available: bool = False
    mock_fixture_available: bool = True
    selected_for_run: bool = False
    requires_approval: bool = False
    default_enabled: bool = False
    blocked_by_default: bool = False
    supports_keyword_search: bool = True
    supports_semantic_search: bool = False
    supports_neural_search: bool = False
    supports_google_grounding: bool = False
    supports_answer_generation: bool = False
    supports_content_extraction: bool = False
    supports_pdf_content: bool = False
    supports_github_content: bool = False
    supports_domain_filtering: bool = False
    supports_date_filtering: bool = False
    supports_highlights: bool = False
    supports_full_text: bool = False
    supports_structured_sources: bool = True
    supports_citations: bool = True
    supports_search_cache: bool = True
    base_cost_per_1000_requests: float | None = None
    cost_per_extra_result: float | None = None
    cost_per_1000_pages: float | None = None
    summary_cost_per_1000_pages: float | None = None
    pricing_source: str = "manual_assumption"
    pricing_last_checked_at: str = "unknown"
    pricing_is_estimate: bool = True
    cost_notes: str = "Search cost is tracked as estimate unless provider reports exact cost."
    best_for: list[str] = Field(default_factory=list)
    avoid_for: list[str] = Field(default_factory=list)
    default_for_tasks: list[str] = Field(default_factory=list)
    fallback_provider_ids: list[str] = Field(default_factory=list)
    max_results_default: int = 5
    max_results_hard_limit: int = 10
    content_fetch_default: int = 0
    content_fetch_hard_limit: int = 3
    cache_ttl_hours: int = 24
    allowed_agents: list[str] = Field(default_factory=lambda: ["research_agent"])
    requires_allow_web_search: bool = True
    requires_live_mode_for_real_search: bool = True
    allowed_domains_optional: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)
    max_cost_per_run_recommended: float = 0.02
    must_store_sources: bool = True
    must_not_pretend_if_disabled: bool = True
    reasons: list[str] = Field(default_factory=list)


class SearchSelectionRequest(BaseModel):
    query: str
    agent_id: str = "research_agent"
    allow_web_search: bool = False
    mode: Literal["mock", "live"] = "mock"
    explicit_provider_id: str | None = None
    max_results: int = 5
    budget_usd: float = 0.02
    allow_gated: bool = False
    combined_search: bool = False


class SearchSelectionResult(BaseModel):
    search_needed: bool
    selected_provider_id: str | None = None
    search_unavailable: bool = False
    combined_search_used: bool = False
    provider_ids: list[str] = Field(default_factory=list)
    reason: str


class SearchSource(BaseModel):
    title: str
    url: str
    domain: str | None = None
    published_date: str | None = None
    retrieved_at: str
    snippet: str = ""
    content_fetched: bool = False


class SearchRequest(BaseModel):
    query: str
    provider_id: str | None = None
    max_results: int = 5
    mode: Literal["mock", "live"] = "mock"
    allow_web_search: bool = False
    fetch_contents: bool = False
    run_id: str | None = None
    project_id: str | None = None
    agent_name: str = "Research Agent"


class SearchResultPayload(BaseModel):
    research_used: bool
    search_provider_id: str | None
    query_plan: list[str] = Field(default_factory=list)
    sources: list[SearchSource] = Field(default_factory=list)
    brief: str = ""
    limitations: list[str] = Field(default_factory=list)
    cost: dict = Field(default_factory=dict)
    cache_hit: bool = False
    mock_fixture: bool = False
    error_type: str | None = None
    error_message: str | None = None
