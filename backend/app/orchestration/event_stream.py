from datetime import UTC, datetime

from app.core.cost_estimator import estimate_cost_usd, estimate_tokens
from app.core.models import RunEvent


def build_event(
    *,
    agent_name: str,
    agent_role: str,
    action_summary: str,
    input_summary: str,
    output_summary: str,
    model_used: str,
) -> RunEvent:
    input_tokens = estimate_tokens(input_summary)
    output_tokens = estimate_tokens(output_summary)
    return RunEvent(
        timestamp=datetime.now(UTC),
        agent_name=agent_name,
        agent_role=agent_role,
        status="completed",
        action_summary=action_summary,
        input_summary=input_summary,
        output_summary=output_summary,
        model_used=model_used,
        estimated_input_tokens=input_tokens,
        estimated_output_tokens=output_tokens,
        estimated_cost_usd=estimate_cost_usd(model_used, input_tokens, output_tokens),
    )

