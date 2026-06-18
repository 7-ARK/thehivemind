from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException

from app.approvals.schemas import ApprovalDecision, ApprovalRequest
from app.core.config import get_settings


class ApprovalStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_settings().approval_path
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[ApprovalRequest]:
        approvals = []
        for path in sorted(self.root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            approvals.append(ApprovalRequest.model_validate_json(path.read_text(encoding="utf-8")))
        return approvals

    def pending(self) -> list[ApprovalRequest]:
        return [approval for approval in self.list() if approval.status == "pending"]

    def get(self, approval_id: str) -> ApprovalRequest:
        path = self._path(approval_id)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Approval request not found.")
        return ApprovalRequest.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, approval: ApprovalRequest) -> ApprovalRequest:
        self._path(approval.id).write_text(approval.model_dump_json(indent=2), encoding="utf-8")
        return approval

    def create_many(self, approvals: list[ApprovalRequest]) -> list[ApprovalRequest]:
        return [self.save(approval) for approval in approvals]

    def decide(self, approval_id: str, decision: ApprovalDecision) -> ApprovalRequest:
        approval = self.get(approval_id)
        if approval.status != "pending":
            raise HTTPException(status_code=400, detail=f"Approval is already {approval.status}.")
        updated = approval.model_copy(
            update={
                "status": decision.decision,
                "decided_at": datetime.now(UTC).isoformat(),
                "decision_reason": decision.reason,
            }
        )
        return self.save(updated)

    def _path(self, approval_id: str) -> Path:
        safe_id = approval_id.replace("/", "_").replace("\\", "_")
        return self.root / f"{safe_id}.json"
