from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


QualityLevel = Literal["low", "medium", "high", "very_high", "unknown"]
SpeedLevel = Literal["slow", "medium", "fast", "very_fast", "unknown"]
CostLevel = Literal["free", "very_low", "low", "medium", "high", "very_high", "unknown"]
ModelStatus = Literal["active", "disabled", "planned", "experimental"]


class ModelRegistryEntry(BaseModel):
    id: str
    display_name: str
    provider: str
    provider_model_name: str
    status: ModelStatus = "active"
    enabled: bool = True
    available_for_live: bool = True
    requires_approval: bool = False
    blocked_by_default: bool = False
    default_service_tier: str | None = None
    fallback_models: list[str] = Field(default_factory=list)

    supports_text: bool = True
    supports_vision: bool = False
    supports_audio: bool = False
    supports_video: bool = False
    supports_multimodal: bool = False
    supports_json: bool = True
    supports_structured_output: bool = False
    supports_function_calling: bool = False
    supports_tool_use: bool = False
    supports_web_search: bool = False
    supports_url_context: bool = False
    supports_code_execution: bool = False
    supports_embeddings: bool = False
    supports_long_context: bool = False
    supports_streaming: bool = True

    reasoning_quality: QualityLevel = "unknown"
    coding_quality: QualityLevel = "unknown"
    writing_quality: QualityLevel = "unknown"
    research_quality: QualityLevel = "unknown"
    planning_quality: QualityLevel = "unknown"
    math_quality: QualityLevel = "unknown"
    qa_quality: QualityLevel = "unknown"
    summarization_quality: QualityLevel = "unknown"
    instruction_following_quality: QualityLevel = "unknown"

    speed_level: SpeedLevel = "unknown"
    latency_notes: str = "unknown"
    reliability_notes: str = "unknown"
    rate_limit_notes: str = "unknown"
    context_window_tokens: int | str = "unknown"
    max_output_tokens_safe_default: int = 500
    max_output_tokens_hard_limit_if_known: int | str = "unknown"

    input_cost_per_1m_tokens: float | None = None
    output_cost_per_1m_tokens: float | None = None
    cached_input_cost_per_1m_tokens: float | None = None
    reasoning_cost_per_1m_tokens: float | None = None
    image_input_cost_if_known: float | str | None = "unknown"
    search_cost_if_known: float | str | None = "unknown"
    currency: str = "USD"
    pricing_source: str = "manual_assumption"
    pricing_last_checked_at: str = "unknown"
    pricing_is_estimate: bool = True
    pricing_notes: str = "Registry pricing is for safety estimates only; actual spend comes from provider usage/billing."

    architecture_family: str = "unknown"
    model_size_if_public: str = "unknown"
    training_cutoff_if_known: str = "unknown"
    open_weights: bool | str = "unknown"
    hosted_provider: str = "unknown"
    underlying_provider_if_openrouter: str | None = None
    modalities: list[str] = Field(default_factory=lambda: ["text"])
    tooling_notes: str = "unknown"
    known_limitations: list[str] = Field(default_factory=list)
    known_strengths: list[str] = Field(default_factory=list)
    known_weaknesses: list[str] = Field(default_factory=list)

    best_for: list[str] = Field(default_factory=list)
    okay_for: list[str] = Field(default_factory=list)
    avoid_for: list[str] = Field(default_factory=list)
    default_agent_roles: list[str] = Field(default_factory=list)
    example_tasks: list[str] = Field(default_factory=list)
    bad_task_examples: list[str] = Field(default_factory=list)

    max_cost_per_call_recommended: float = 0.01
    max_cost_per_run_recommended: float = 0.05
    allowed_in_mock: bool = True
    allowed_in_live: bool = True
    allowed_for_ceo: bool = False
    allowed_for_research: bool = False
    allowed_for_website: bool = False
    allowed_for_file_builder: bool = False
    allowed_for_qa: bool = False
    allowed_for_operations: bool = False
    allowed_for_user_visible_outputs: bool = True
    requires_human_approval_for_live: bool = False
    requires_human_approval_for_search: bool = False
    requires_human_approval_for_high_cost: bool = False

    selection_tags: list[str] = Field(default_factory=list)
    cost_level: CostLevel = "unknown"
    quality_level: QualityLevel = "unknown"
    preferred_for_low_budget: bool = False
    preferred_for_high_accuracy: bool = False
    preferred_for_search: bool = False
    preferred_for_coding: bool = False
    preferred_for_multimodal: bool = False
    preferred_for_fast_routing: bool = False
    approved_for_auto_selection: bool = True
    curated_tier: Literal["core", "fallback", "experimental", "planned"] = "core"
    promotion_reason: str = "Curated manually for TheHiveMind v1."
    auto_selectable: bool = True
    search_tool_compatible: bool = False
    notes_for_selector: str = ""


class ProviderRegistryEntry(BaseModel):
    id: str
    display_name: str
    key_setting_names: list[str] = Field(default_factory=list)
    live_enabled_setting: str | None = None
    search_enabled_setting: str | None = None
    notes: str = ""


class ModelAvailability(BaseModel):
    model_id: str
    provider: str
    available: bool
    available_for_live: bool
    provider_configured: bool
    search_enabled: bool
    blocked_by_default: bool = False
    requires_approval: bool = False
    auto_selectable: bool = False
    selectable_in_mock: bool = False
    selectable_in_live_without_approval: bool = False
    reasons: list[str] = Field(default_factory=list)


class ModelSelectionRequest(BaseModel):
    command: str
    agent_id: str
    agent_role: str | None = None
    agent_task: str
    mode: Literal["mock", "live"] = "mock"
    run_type: str = "business_launch_plan"
    required_capabilities: list[str] = Field(default_factory=list)
    allowed_model_ids: list[str] = Field(default_factory=list)
    excluded_model_ids: list[str] = Field(default_factory=list)
    preferred_tags: list[str] = Field(default_factory=list)
    max_cost_usd: float = 0.01
    live_calls_allowed: bool = False
    search_enabled: bool = False
    approval_ids: list[str] = Field(default_factory=list)
    context_packet: dict[str, Any] = Field(default_factory=dict)


class CostGuard(BaseModel):
    within_budget: bool
    max_allowed_cost: float


class RejectedModel(BaseModel):
    model_id: str
    reason: str


class ModelSelectionResult(BaseModel):
    selected_model_id: str
    provider: str
    reason: str
    confidence: float
    estimated_risk: Literal["low", "medium", "high"]
    requires_approval: bool
    fallback_model_id: str | None = None
    why_not_others: list[RejectedModel] = Field(default_factory=list)
    cost_guard: CostGuard
    compact_candidates_used: list[dict[str, Any]] = Field(default_factory=list)
    full_details_loaded_for: list[str] = Field(default_factory=list)
