from __future__ import annotations

from app.agent_registry.registry_loader import AgentRegistryLoader
from app.agent_registry.schemas import AgentPlanRequest, AgentPlanResult, PlannedAgent, SkippedAgent
from app.core.config import Settings, get_settings
from app.model_registry.selector_service import DynamicModelSelector
from app.search_tools.registry_loader import SearchRegistryLoader
from app.search_tools.schemas import SearchSelectionRequest
from app.search_tools.search_selector import SearchSelector


class AgentPlannerService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.loader = AgentRegistryLoader(self.settings)
        self.selector = DynamicModelSelector(self.settings)
        self.search_selector = SearchSelector(self.settings)
        self.search_loader = SearchRegistryLoader(self.settings)

    def plan(self, request: AgentPlanRequest, *, include_model_selection: bool = True) -> AgentPlanResult:
        constraints = _dedupe(_negative_constraints(request.command, self.loader.rules()))
        blocked_actions = _dedupe(_blocked_actions_from_constraints(constraints))
        workflow = _workflow_for(request)
        search_selection = self.search_selector.select(
            SearchSelectionRequest(
                query=request.command,
                allow_web_search=request.allow_search,
                mode=request.mode,
                max_results=5,
            )
        )
        selected_ids = self._selected_ids(workflow, request, constraints)
        selected: list[PlannedAgent] = []
        skipped: list[SkippedAgent] = []

        agents_by_id = {agent.id: agent for agent in self.loader.agents()}
        for agent_id in selected_ids:
            agent = agents_by_id[agent_id]
            planned = PlannedAgent(
                agent_id=agent.id,
                objective=_objective_for(agent.id, request.command),
                required_capabilities=_required_capabilities(agent.id, request),
                required_model_capabilities=_required_model_capabilities(agent.id, request),
                required_search_tool_capabilities=_required_search_tool_capabilities(agent.id, request),
                allowed_tools=_allowed_tools(agent.id, agent.allowed_tools, request, constraints),
                allowed_files=agent.allowed_file_scopes,
                blocked_actions=_dedupe([*agent.blocked_actions, *blocked_actions]),
                constraints=_dedupe(constraints),
                needs_model_selection=agent.id != "safe_command_runner",
            )
            if include_model_selection and planned.needs_model_selection:
                try:
                    selection = self.selector.select_for_agent(
                        command=request.command,
                        agent_id=agent.id,
                        agent_role=agent.display_name,
                        agent_task=planned.objective,
                        mode=request.mode,
                        run_type=workflow,
                        required_capabilities=planned.required_model_capabilities,
                        preferred_tags=agent.preferred_model_tags,
                        max_cost_usd=min(request.max_cost_usd, self.settings.max_cost_per_call_usd),
                        project_id=request.project_id,
                    )
                    planned.selected_model = selection.model_dump()
                except ValueError as exc:
                    planned.selected_model = {"error": str(exc)}
            if agent.id == "research_agent" and search_selection.selected_provider_id:
                provider = self.search_loader.get_provider(search_selection.selected_provider_id)
                if provider:
                    provider = self.search_loader._with_availability(
                        provider,
                        mode=request.mode,
                        allow_web_search=request.allow_search,
                        allow_gated=False,
                    )
                planned.selected_search_provider = provider.model_dump() if provider else {"id": search_selection.selected_provider_id}
            selected.append(planned)

        for agent in self.loader.agents():
            if agent.id in selected_ids:
                continue
            skipped.append(SkippedAgent(agent_id=agent.id, reason=_skip_reason(agent.id, workflow, request)))

        search_unavailable = search_selection.search_unavailable
        notes = []
        if "file_writes" in constraints and request.allow_file_writes:
            notes.append("Your prompt restricted file writes, so the system disabled those actions for this run.")
        if "commands" in constraints and request.allow_safe_commands:
            notes.append("Your prompt restricted command execution, so the system disabled those actions for this run.")
        if search_unavailable:
            notes.append(search_selection.reason)

        return AgentPlanResult(
            run_goal=request.command,
            selected_workflow=workflow,
            selected_agents=selected,
            skipped_agents=skipped,
            safety_constraints=constraints,
            blocked_actions=blocked_actions,
            memory_requirements=["project_state.md", "latest final_report.md summary", "latest qa_review.md summary", "model_registry_notes.md"],
            approval_required=False,
            search_needed=search_selection.search_needed,
            search_unavailable=search_unavailable,
            selected_search_provider=self._selected_provider_payload(search_selection.selected_provider_id, request),
            combined_search_used=search_selection.combined_search_used,
            proposed_agent_requires_review=False,
            notes=notes,
        )

    def _selected_provider_payload(self, provider_id: str | None, request: AgentPlanRequest) -> dict | None:
        if not provider_id:
            return None
        provider = self.search_loader.get_provider(provider_id)
        if not provider:
            return {"id": provider_id}
        hydrated = self.search_loader._with_availability(
            provider,
            mode=request.mode,
            allow_web_search=request.allow_search,
            allow_gated=False,
        )
        return hydrated.model_dump()

    def _selected_ids(self, workflow: str, request: AgentPlanRequest, constraints: list[str]) -> list[str]:
        if workflow == "provider_test":
            return ["provider_test_agent"]
        if workflow == "website_update":
            agents = []
            if _search_needed(request.command):
                agents.append("research_agent")
            agents.extend(["website_agent", "qa_agent"])
            if request.allow_safe_commands and "commands" not in constraints:
                agents.append("safe_command_runner")
            return agents
        if workflow == "research_only":
            return ["research_agent", "qa_agent"]
        return ["ceo_agent", "research_agent", "content_agent", "operations_agent", "qa_agent"]


def _workflow_for(request: AgentPlanRequest) -> str:
    command = request.command.lower()
    if request.run_type == "provider_test":
        return "provider_test"
    if request.run_type in {"research", "research_only"}:
        return "research_only"
    if request.run_type == "website_update":
        return "website_update"
    if _research_only_requested(command):
        return "research_only"
    if any(term in command for term in ("homepage", "website", "edit file", "fix website", "remake website")):
        return "website_update"
    return "business_launch_plan"


def _negative_constraints(command: str, rules: dict) -> list[str]:
    lowered = command.lower()
    constraints = []
    for label, phrases in rules.get("negative_constraints", {}).items():
        if any(phrase in lowered for phrase in phrases):
            constraints.append(label)
    return constraints


def _blocked_actions_from_constraints(constraints: list[str]) -> list[str]:
    mapping = {
        "deploy": "deploy",
        "package_install": "package_install",
        "external_actions": "external_actions",
        "email": "customer_messaging",
        "social_posting": "social_posting",
        "file_writes": "file_write",
        "commands": "safe_command",
        "gpt-5.5": "gpt-5.5",
    }
    return [mapping[item] for item in constraints if item in mapping]


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _objective_for(agent_id: str, command: str) -> str:
    objectives = {
        "ceo_agent": "Plan the controlled workflow and safety handoffs.",
        "research_agent": "Research or summarize relevant context without pretending to browse if search is disabled.",
        "content_agent": "Draft safe, reviewable copy and content inputs.",
        "operations_agent": "Define manual operating flow and approval checkpoints.",
        "website_agent": "Update website project files within the approved website/ scope.",
        "file_builder_agent": "Convert approved file requirements into safe file actions.",
        "safe_command_runner": "Run allowlisted validation commands and log stdout/stderr/cwd.",
        "qa_agent": "Review outputs, constraints, file changes, and command results.",
        "provider_test_agent": "Run one tiny live provider connectivity test.",
        "project_workspace_manager": "Update project state and manifest from actual changes.",
    }
    return f"{objectives.get(agent_id, 'Perform approved task.')} Command: {command[:500]}"


def _required_capabilities(agent_id: str, request: AgentPlanRequest) -> list[str]:
    return _dedupe([*_required_model_capabilities(agent_id, request), *_required_search_tool_capabilities(agent_id, request)])


def _required_model_capabilities(agent_id: str, request: AgentPlanRequest) -> list[str]:
    caps: list[str] = []
    if agent_id in {"website_agent", "file_builder_agent"}:
        caps.extend(["coding", "tools", "json"])
    if agent_id == "research_agent":
        caps.extend(["json", "summarization"])
    if agent_id == "qa_agent":
        caps.append("json")
    return caps


def _required_search_tool_capabilities(agent_id: str, request: AgentPlanRequest) -> list[str]:
    if agent_id == "research_agent" and _search_needed(request.command):
        return ["web_search"]
    return []


def _allowed_tools(agent_id: str, tools: list[str], request: AgentPlanRequest, constraints: list[str]) -> list[str]:
    filtered = list(tools)
    if not request.allow_search or "external_actions" in constraints:
        filtered = [tool for tool in filtered if tool != "web_search"]
    if not request.allow_file_writes or "file_writes" in constraints:
        filtered = [tool for tool in filtered if tool != "project_file_write"]
    if not request.allow_safe_commands or "commands" in constraints:
        filtered = [tool for tool in filtered if tool != "safe_command"]
    return filtered


def _search_needed(command: str) -> bool:
    lowered = _strip_negated_search_phrases(command.lower())
    return any(term in lowered for term in ("research", "competitor", "latest", "current", "web search", "browse", "market trends", "sources"))


def _strip_negated_search_phrases(command: str) -> str:
    for phrase in (
        "do not run live web search",
        "don't run live web search",
        "do not use live web search",
        "don't use live web search",
        "do not run web search",
        "don't run web search",
        "do not web search",
        "don't web search",
        "do not search",
        "don't search",
        "no live web search",
        "no web search",
        "without live web search",
        "without web search",
        "do not browse",
        "don't browse",
        "no browsing",
        "without browsing",
    ):
        command = command.replace(phrase, "")
    return command


def _research_only_requested(command: str) -> bool:
    return "research" in command and (
        "research only" in command
        or "only research" in command
        or not any(term in command for term in ("website", "homepage", "file", "copy", "update"))
    )


def _skip_reason(agent_id: str, workflow: str, request: AgentPlanRequest) -> str:
    if workflow == "website_update":
        return "Not needed for website-only update workflow."
    if workflow == "research_only":
        return "Not needed for research-only workflow."
    if workflow == "provider_test":
        return "Provider test runs use only the Provider Test Agent."
    return f"Not selected for {request.run_type}."
