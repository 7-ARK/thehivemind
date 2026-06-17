from pydantic import BaseModel, Field
from fastapi import HTTPException

from app.core.config import Settings, get_settings
from app.core.cost_estimator import estimate_cost, estimate_messages_tokens
from app.orchestration.agent_context import AgentExecutionContext
from app.providers.provider_router import generate_with_provider
from app.storage.usage_store import UsageStore


class AgentOutput(BaseModel):
    agent_name: str
    model: str
    provider: str
    output_text: str
    structured_summary: str
    artifacts_to_create: list[dict] = Field(default_factory=list)
    file_actions: list[dict] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    usage_log_id: str | None = None
    estimated_cost_usd: float = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 1


async def run_llm_agent(
    context: AgentExecutionContext,
    system_prompt: str,
    user_prompt: str,
    *,
    settings: Settings | None = None,
    usage_store: UsageStore | None = None,
    request_type: str = "agent_execution",
) -> AgentOutput:
    settings = settings or get_settings()
    messages = [
        {
            "role": "system",
            "content": (
                f"{system_prompt}\n"
                "Return practical outputs only: decisions, generated content, file actions, summaries, and next steps. "
                "Do not include hidden chain-of-thought or secrets."
            ),
        },
        {"role": "user", "content": user_prompt},
    ]
    input_tokens = estimate_messages_tokens(messages)
    estimated = estimate_cost(context.model, input_tokens, context.max_output_tokens)
    if estimated.estimated_cost_usd > context.max_cost_usd:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Estimated agent call cost ${estimated.estimated_cost_usd:.6f} exceeds "
                f"remaining agent budget ${context.max_cost_usd:.6f}."
            ),
        )

    if context.mode == "mock":
        text = _mock_agent_text(context)
        output_tokens = max(1, len(text) // 4)
        cost = estimate_cost(context.model, input_tokens, output_tokens).estimated_cost_usd
        return AgentOutput(
            agent_name=context.agent_name,
            model=context.model,
            provider=context.provider,
            output_text=text,
            structured_summary=f"Mock {context.agent_name} output for {context.task_objective}",
            next_steps=["Review output", "Continue with the next safe agent step"],
            estimated_cost_usd=cost,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    response, usage_log_id = await generate_with_provider(
        provider=context.provider,
        model=context.model,
        mode="live",
        messages=messages,
        max_output_tokens=context.max_output_tokens,
        temperature=0.2,
        service_tier=settings.ceo_service_tier if context.model == settings.ceo_model else None,
        run_id=context.run_id,
        task_id=f"{context.run_id}:{request_type}",
        agent_name=context.agent_name,
        agent_role=context.agent_role,
        project_id=context.project_id,
        request_type=request_type,
        settings=settings,
        usage_store=usage_store,
    )
    return AgentOutput(
        agent_name=context.agent_name,
        model=response.model,
        provider=response.provider if response.provider != "mock" else context.provider,
        output_text=response.text,
        structured_summary=response.text[:500],
        usage_log_id=usage_log_id,
        estimated_cost_usd=response.estimated_cost_usd,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        latency_ms=response.latency_ms,
    )


def _mock_agent_text(context: AgentExecutionContext) -> str:
    return (
        f"# {context.agent_name} Output\n\n"
        f"## Objective\n{context.task_objective}\n\n"
        f"## Decision Summary\n- Mode: {context.mode}\n- Project: {context.project_id}\n"
        "- External actions remain disabled.\n\n"
        "## Next Steps\n- Save artifacts.\n- Pass only relevant summaries to the next agent.\n"
    )
