import { AlertTriangle, CheckCircle2, ShieldCheck, XCircle } from "lucide-react";
import { ApprovalRequest } from "../../types";

interface Props {
  approvals: ApprovalRequest[];
  decidingId?: string | null;
  onDecision: (approvalId: string, decision: "approved" | "rejected") => void;
  onRunWithApproval: () => void;
}

export default function ApprovalPanel({ approvals, decidingId, onDecision, onRunWithApproval }: Props) {
  const approved = approvals.filter((approval) => approval.status === "approved");
  const allApproved = approvals.length > 0 && approved.length === approvals.length;
  const rejected = approvals.some((approval) => approval.status === "rejected");

  return (
    <section className="bg-[#1a1b1e] border border-[#fab005]/30 rounded-lg p-5 space-y-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-[#fab005] shrink-0 mt-0.5" />
        <div>
          <h3 className="text-sm font-bold text-[#e9ecef]">Approval Required</h3>
          <p className="text-xs text-[#909296] mt-1">
            Risky requests in the command are detected automatically, but command text is not approval. Confirm through these cards before running.
          </p>
        </div>
      </div>

      <div className="space-y-3">
        {approvals.map((approval) => (
          <div key={approval.id} className="bg-[#141517] border border-[#2c2e33] rounded p-4">
            <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3">
              <div>
                <div className="flex flex-wrap gap-2 text-[10px] font-mono mb-2">
                  <span className={riskClass(approval.risk_level)}>{approval.risk_level.toUpperCase()}</span>
                  <span className="text-[#909296] bg-[#25262b] border border-[#2c2e33] rounded px-2 py-1">{approval.approval_type}</span>
                  <span className={statusClass(approval.status)}>{approval.status.toUpperCase()}</span>
                </div>
                <h4 className="text-sm font-bold text-[#e9ecef]">{approval.title}</h4>
                <p className="text-xs text-[#909296] mt-2">{approval.reason}</p>
                <p className="text-xs text-[#e9ecef] mt-2">
                  <span className="text-[#909296]">Requested action:</span> {approval.requested_action}
                </p>
                <div className="flex flex-wrap gap-3 text-[10px] text-[#909296] font-mono mt-3">
                  {approval.estimated_cost_usd != null && <span>Estimate: ${approval.estimated_cost_usd.toFixed(4)}</span>}
                  {approval.model && <span>Model: {approval.model}</span>}
                  {approval.provider && <span>Provider: {approval.provider}</span>}
                </div>
              </div>
              <div className="flex gap-2 shrink-0">
                <button
                  onClick={() => onDecision(approval.id, "approved")}
                  disabled={approval.status !== "pending" || decidingId === approval.id}
                  className="bg-[#20c997] disabled:bg-[#2c2e33] disabled:text-[#909296] text-[#141517] px-3 py-2 rounded text-xs font-bold flex items-center gap-1.5"
                >
                  <CheckCircle2 className="w-4 h-4" />
                  Approve
                </button>
                <button
                  onClick={() => onDecision(approval.id, "rejected")}
                  disabled={approval.status !== "pending" || decidingId === approval.id}
                  className="bg-[#25262b] disabled:opacity-60 border border-[#2c2e33] text-rose-300 px-3 py-2 rounded text-xs font-bold flex items-center gap-1.5"
                >
                  <XCircle className="w-4 h-4" />
                  Reject
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-t border-[#2c2e33] pt-4">
        <p className="text-xs text-[#909296]">
          Safer alternative: keep mock mode on, leave CEO live off, and avoid deployment, package installs, payments, or external messaging.
        </p>
        <button
          onClick={onRunWithApproval}
          disabled={!allApproved || rejected}
          className="bg-[#20c997] hover:bg-[#1db184] disabled:bg-[#2c2e33] disabled:text-[#909296] text-[#141517] px-4 py-2.5 rounded text-xs font-bold flex items-center justify-center gap-2"
        >
          <ShieldCheck className="w-4 h-4" />
          Run with approval
        </button>
      </div>
    </section>
  );
}

function riskClass(risk: ApprovalRequest["risk_level"]): string {
  const base = "rounded px-2 py-1 border ";
  if (risk === "critical") return `${base}text-rose-300 border-rose-500/30 bg-rose-500/10`;
  if (risk === "high") return `${base}text-[#fab005] border-[#fab005]/30 bg-[#fab005]/10`;
  if (risk === "medium") return `${base}text-sky-300 border-sky-500/30 bg-sky-500/10`;
  return `${base}text-[#20c997] border-[#20c997]/20 bg-[#20c997]/10`;
}

function statusClass(status: ApprovalRequest["status"]): string {
  const base = "rounded px-2 py-1 border ";
  if (status === "approved") return `${base}text-[#20c997] border-[#20c997]/20 bg-[#20c997]/10`;
  if (status === "rejected") return `${base}text-rose-300 border-rose-500/30 bg-rose-500/10`;
  return `${base}text-[#909296] border-[#2c2e33] bg-[#25262b]`;
}
