from __future__ import annotations

from app.core.config import Settings, get_settings
from app.model_registry.availability_service import ModelAvailabilityService
from app.model_registry.pricing_service import ModelPricingService
from app.model_registry.prompt_builder import SelectorPromptBuilder, extract_user_constraints
from app.model_registry.registry_loader import ModelRegistryLoader
from app.model_registry.schemas import CostGuard, ModelRegistryEntry, ModelSelectionRequest, ModelSelectionResult, RejectedModel


class DynamicModelSelector:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.loader = ModelRegistryLoader(self.settings)
        self.availability = ModelAvailabilityService(self.settings, self.loader)
        self.pricing = ModelPricingService()
        self.prompt_builder = SelectorPromptBuilder(self.settings, self.loader)

    def select(self, request: ModelSelectionRequest) -> ModelSelectionResult:
        candidates, rejected = self._filter_candidates(request)
        if not candidates:
            fallback = self._fallback(request, rejected)
            if fallback:
                candidates = [fallback]
            else:
                raise ValueError("No valid model available under current constraints.")

        ranked = sorted(candidates, key=lambda model: self._score(model, request), reverse=True)
        selected = ranked[0]
        compact = [self.loader.compact_summary(model) for model in ranked[:6]]
        full_details = [model.id for model in ranked[:3]] if len(ranked) > 1 and abs(self._score(ranked[0], request) - self._score(ranked[min(1, len(ranked) - 1)], request)) < 2 else []
        why_not = [
            RejectedModel(model_id=model.id, reason=self._why_not(model, selected, request))
            for model in ranked[1:6]
        ]
        why_not.extend(rejected[:6])
        risk = "high" if selected.requires_approval or selected.blocked_by_default else "low"
        reason = self._reason(selected, request)
        return ModelSelectionResult(
            selected_model_id=selected.id,
            provider=selected.provider,
            reason=reason,
            confidence=min(0.98, max(0.45, self._score(selected, request) / 12)),
            estimated_risk=risk,
            requires_approval=self._requires_approval(selected, request),
            fallback_model_id=selected.fallback_models[0] if selected.fallback_models else None,
            why_not_others=why_not,
            cost_guard=CostGuard(
                within_budget=self.pricing.within_budget(selected, request.max_cost_usd),
                max_allowed_cost=request.max_cost_usd,
            ),
            compact_candidates_used=compact,
            full_details_loaded_for=full_details,
        )

    def select_for_agent(
        self,
        *,
        command: str,
        agent_id: str,
        agent_role: str,
        agent_task: str,
        mode: str,
        run_type: str,
        required_capabilities: list[str],
        preferred_tags: list[str],
        max_cost_usd: float,
        project_id: str | None = None,
        approval_ids: list[str] | None = None,
    ) -> ModelSelectionResult:
        context = self.prompt_builder.context_packet(command=command, project_id=project_id)
        excluded = _excluded_models_from_command(command)
        return self.select(
            ModelSelectionRequest(
                command=command,
                agent_id=agent_id,
                agent_role=agent_role,
                agent_task=agent_task,
                mode=mode,  # type: ignore[arg-type]
                run_type=run_type,
                required_capabilities=required_capabilities,
                excluded_model_ids=excluded,
                preferred_tags=preferred_tags,
                max_cost_usd=max_cost_usd,
                live_calls_allowed=self.settings.is_live_allowed(),
                search_enabled=any(
                    [self.settings.enable_openai_web_search, self.settings.enable_gemini_grounding, self.settings.enable_openrouter_search]
                ),
                approval_ids=approval_ids or [],
                context_packet=context,
            )
        )

    def _filter_candidates(self, request: ModelSelectionRequest) -> tuple[list[ModelRegistryEntry], list[RejectedModel]]:
        user_constraints = set(extract_user_constraints(request.command))
        cheap_only = _cheap_only(request.command)
        search_required = "search" in request.required_capabilities
        candidates: list[ModelRegistryEntry] = []
        rejected: list[RejectedModel] = []
        for model in self.loader.models():
            reason = self._reject_reason(model, request, user_constraints, cheap_only, search_required)
            if reason:
                rejected.append(RejectedModel(model_id=model.id, reason=reason))
            else:
                candidates.append(model)
        return candidates, rejected

    def _reject_reason(
        self,
        model: ModelRegistryEntry,
        request: ModelSelectionRequest,
        user_constraints: set[str],
        cheap_only: bool,
        search_required: bool,
    ) -> str | None:
        if request.allowed_model_ids and model.id not in request.allowed_model_ids:
            return "Not in request allowlist."
        if model.id in request.excluded_model_ids:
            return "Excluded by user constraint."
        if (not model.approved_for_auto_selection or not model.auto_selectable) and not _approval_allows_model(model, request):
            return "Model is not approved for automatic selection."
        if model.curated_tier == "planned" or model.status == "planned":
            return "Model is planned/discovery-only and not selectable."
        if model.id.startswith("gpt-5.5") and "gpt-5.5" in user_constraints:
            return "User said not to use GPT-5.5."
        if cheap_only and model.cost_level in {"high", "very_high"}:
            return "Cheap-only command filtered high-cost model."
        if not _allowed_for_agent(model, request.agent_id):
            return f"Model is not allowed for agent role {request.agent_id}."
        availability = self.availability.availability(model, mode=request.mode, search_required=search_required)
        if not availability.available:
            return "; ".join(availability.reasons) or "Unavailable."
        if "search" in request.required_capabilities and not model.supports_web_search:
            return "Search required but model does not support search."
        if "tools" in request.required_capabilities and not model.supports_tool_use:
            return "Tool use required but model does not support tools."
        if "vision" in request.required_capabilities and not model.supports_vision:
            return "Vision required but model does not support vision."
        if model.blocked_by_default and not _approval_allows_model(model, request):
            return "Model is blocked by default and no approval was supplied."
        if model.requires_human_approval_for_high_cost and not self.pricing.within_budget(model, request.max_cost_usd):
            return "Model exceeds the request cost guard."
        return None

    def _fallback(self, request: ModelSelectionRequest, rejected: list[RejectedModel]) -> ModelRegistryEntry | None:
        if "search" in request.required_capabilities:
            return None
        blocked = {item.model_id for item in rejected if "User said not to use" in item.reason}
        for model_id in self.loader.rules().get("safe_fallback_order", []):
            model = self.loader.get_model(model_id)
            if model and model.id not in blocked and _allowed_for_agent(model, request.agent_id):
                availability = self.availability.availability(model, mode="mock" if request.mode == "mock" else request.mode)
                if availability.available:
                    return model
        return None

    def _score(self, model: ModelRegistryEntry, request: ModelSelectionRequest) -> float:
        score = 0.0
        tags = set(model.selection_tags)
        score += len(tags & set(request.preferred_tags)) * 2
        if model.preferred_for_low_budget or model.cost_level in {"very_low", "low"}:
            score += 2
        if _cheap_only(request.command) and model.cost_level in {"very_low", "low"}:
            score += 4
        if "coding" in request.required_capabilities and model.preferred_for_coding:
            score += 4
        if "coding" in request.required_capabilities and model.id == self.settings.real_coding_agent_model:
            score += 5
        if "search" in request.required_capabilities and model.preferred_for_search:
            score += 4
        if "tools" in request.required_capabilities and model.supports_tool_use:
            score += 2
        if model.max_cost_per_call_recommended <= request.max_cost_usd:
            score += 2
        if model.blocked_by_default:
            score -= 5
        return score

    def _requires_approval(self, model: ModelRegistryEntry, request: ModelSelectionRequest) -> bool:
        if request.mode == "live" and model.requires_human_approval_for_live:
            return not _approval_allows_model(model, request)
        if model.requires_human_approval_for_high_cost and not self.pricing.within_budget(model, request.max_cost_usd):
            return True
        return model.requires_approval and not _approval_allows_model(model, request)

    def _reason(self, model: ModelRegistryEntry, request: ModelSelectionRequest) -> str:
        parts = [f"Selected {model.display_name} for {request.agent_id}."]
        if model.cost_level in {"very_low", "low"}:
            parts.append("It satisfies the low-cost guard.")
        if request.preferred_tags:
            parts.append(f"Matched tags: {', '.join(sorted(set(model.selection_tags) & set(request.preferred_tags)))}.")
        if request.required_capabilities:
            parts.append(f"Required capabilities checked: {', '.join(request.required_capabilities)}.")
        return " ".join(parts)

    def _why_not(self, model: ModelRegistryEntry, selected: ModelRegistryEntry, request: ModelSelectionRequest) -> str:
        if model.cost_level in {"high", "very_high"} and selected.cost_level not in {"high", "very_high"}:
            return "Higher cost than selected model."
        if selected.preferred_for_coding and not model.preferred_for_coding:
            return "Less aligned with coding/file task."
        return "Lower deterministic selector score for this agent/task."


def _allowed_for_agent(model: ModelRegistryEntry, agent_id: str) -> bool:
    normalized = agent_id.lower()
    if normalized in {"ceo_agent", "ceo"}:
        return model.allowed_for_ceo
    if normalized in {"research_agent", "research"}:
        return model.allowed_for_research
    if normalized in {"website_agent", "file_builder_agent", "coding_agent", "real_coding_agent", "coding_worker_agent", "website", "file_builder"}:
        return model.allowed_for_website or model.allowed_for_file_builder
    if normalized in {"qa_agent", "qa"}:
        return model.allowed_for_qa
    if normalized in {"operations_agent", "operations"}:
        return model.allowed_for_operations
    if normalized in {"business_planner_agent", "business_planner", "content_agent", "content", "model_selector_agent", "selector", "safe_command_runner", "provider_test_agent", "project_workspace_manager"}:
        return True
    return False


def _approval_allows_model(model: ModelRegistryEntry, request: ModelSelectionRequest) -> bool:
    return bool(request.approval_ids) and model.id.startswith("gpt-5.5")


def _excluded_models_from_command(command: str) -> list[str]:
    lowered = command.lower()
    excluded = []
    if any(phrase in lowered for phrase in ("do not use gpt-5.5", "don't use gpt-5.5", "no gpt-5.5", "avoid gpt-5.5")):
        excluded.extend(["gpt-5.5", "gpt-5.5:flex"])
    return excluded


def _cheap_only(command: str) -> bool:
    lowered = command.lower()
    return any(phrase in lowered for phrase in ("cheap models only", "cheap worker models", "low cost", "keep cost low", "use cheap"))
