import uuid

from fastapi import HTTPException

from app.approvals.approval_store import ApprovalStore
from app.approvals.risk_policy import evaluate_approval_needs
from app.approvals.schemas import ApprovalRequiredResponse, ApprovalRequest
from app.core.models import RunCreate


class ApprovalEngine:
    def __init__(self, store: ApprovalStore | None = None) -> None:
        self.store = store or ApprovalStore()

    def require_or_create(self, payload: RunCreate) -> ApprovalRequiredResponse | None:
        pending_run_id = str(uuid.uuid4())
        required = evaluate_approval_needs(payload, run_id=pending_run_id)
        if not required:
            return None

        approved_by_type = self._validated_approvals_by_type(payload, payload.approval_ids)
        missing = [approval for approval in required if approval.approval_type not in approved_by_type]
        if not missing:
            self._enforce_unimplemented_action_blocks(approved_by_type)
            return None

        created = self.store.create_many(missing)
        return ApprovalRequiredResponse(
            run_id=pending_run_id,
            project_id=payload.project_id,
            command=payload.command,
            approval_requests=created,
        )

    def _validated_approvals_by_type(self, payload: RunCreate, approval_ids: list[str]) -> dict[str, ApprovalRequest]:
        approvals: dict[str, ApprovalRequest] = {}
        for approval_id in approval_ids:
            approval = self.store.get(approval_id)
            if approval.status == "rejected":
                raise HTTPException(status_code=403, detail=f"Approval {approval_id} was rejected.")
            if approval.status != "approved":
                raise HTTPException(status_code=403, detail=f"Approval {approval_id} is not approved.")
            if approval.command != payload.command:
                raise HTTPException(status_code=403, detail=f"Approval {approval_id} does not match this command.")
            if approval.project_id != payload.project_id:
                raise HTTPException(status_code=403, detail=f"Approval {approval_id} does not match this project.")
            approvals[approval.approval_type] = approval
        return approvals

    def _enforce_unimplemented_action_blocks(self, approvals_by_type: dict[str, ApprovalRequest]) -> None:
        blocked_types = {
            "deployment",
            "package_install",
            "external_api",
            "customer_messaging",
            "social_posting",
            "payment_integration",
            "sensitive_file",
            "dangerous_command",
            "large_overwrite",
        }
        blocked = blocked_types.intersection(approvals_by_type)
        if blocked:
            label = ", ".join(sorted(blocked))
            raise HTTPException(status_code=403, detail=f"Approved but not executed: {label} actions are not implemented in the safe v1 runner.")
