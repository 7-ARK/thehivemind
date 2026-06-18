from typing import Literal

from pydantic import BaseModel, Field


ApprovalStatus = Literal["pending", "approved", "rejected", "expired"]
RiskLevel = Literal["low", "medium", "high", "critical"]
ApprovalDecisionValue = Literal["approved", "rejected"]


class ApprovalRequest(BaseModel):
    id: str
    run_id: str | None = None
    project_id: str | None = None
    command: str
    status: ApprovalStatus
    risk_level: RiskLevel
    approval_type: str
    title: str
    reason: str
    requested_action: str
    estimated_cost_usd: float | None = None
    model: str | None = None
    provider: str | None = None
    created_at: str
    decided_at: str | None = None
    decision_reason: str | None = None
    metadata: dict = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    decision: ApprovalDecisionValue
    reason: str | None = None


class ApprovalRequiredResponse(BaseModel):
    status: Literal["approval_required"] = "approval_required"
    run_id: str
    project_id: str | None = None
    command: str
    approval_requests: list[ApprovalRequest]
