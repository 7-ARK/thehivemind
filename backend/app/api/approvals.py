from fastapi import APIRouter

from app.approvals.approval_store import ApprovalStore
from app.approvals.schemas import ApprovalDecision, ApprovalRequest

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalRequest])
def list_approvals() -> list[ApprovalRequest]:
    return ApprovalStore().list()


@router.get("/pending", response_model=list[ApprovalRequest])
def list_pending_approvals() -> list[ApprovalRequest]:
    return ApprovalStore().pending()


@router.get("/{approval_id}", response_model=ApprovalRequest)
def get_approval(approval_id: str) -> ApprovalRequest:
    return ApprovalStore().get(approval_id)


@router.post("/{approval_id}/decision", response_model=ApprovalRequest)
def decide_approval(approval_id: str, decision: ApprovalDecision) -> ApprovalRequest:
    return ApprovalStore().decide(approval_id, decision)
