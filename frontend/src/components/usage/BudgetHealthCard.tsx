import React from "react";
import { BudgetStatus } from "../../types";
import { AlertTriangle, Clock, ShieldCheck, Landmark } from "lucide-react";

interface BudgetHealthCardProps {
  budget: BudgetStatus;
}

export default function BudgetHealthCard({ budget }: BudgetHealthCardProps) {
  const { monthlyBudget, spent, remaining, percentUsed, status } = budget;

  // Visual classes corresponding to budget thresholds
  let barColorClass = "bg-[#20c997]";
  let textColorClass = "text-[#20c997] border-[#20c997]/20 bg-[#20c997]/5";
  let descriptionText = "Funding remains inside healthy optimal metrics.";
  let Icon = ShieldCheck;

  if (status === "warning") {
    barColorClass = "bg-[#fab005]";
    textColorClass = "text-[#fab005] border-[#fab005]/20 bg-[#fab005]/5";
    descriptionText = "Nearing standard threshold warnings. Monitor model selectors.";
    Icon = AlertTriangle;
  } else if (status === "danger" || status === "exceeded" || percentUsed > 85) {
    barColorClass = "bg-rose-500";
    textColorClass = "text-rose-400 border-rose-500/20 bg-rose-500/5";
    descriptionText = "Immediate budget constraints. Conserve expensive endpoints.";
    Icon = AlertTriangle;
  }

  // Cap display percentage to prevent UI overflow on exceeded states
  const displayPercent = Math.min(percentUsed, 100);

  return (
    <div id="budget-health-card" className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5 mb-6 relative overflow-hidden">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="p-2.5 bg-[#141517] border border-[#2c2e33] rounded shrink-0">
            <Landmark className="w-5 h-5 text-[#909296]" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold tracking-wider uppercase text-[#909296] font-mono">
                Cost Control Guardrail
              </span>
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded border font-semibold ${textColorClass}`}>
                {status.toUpperCase()}
              </span>
            </div>
            <h2 className="text-lg font-medium text-[#e9ecef] mt-1 flex items-baseline gap-1.5">
              <span className="font-semibold">Recorded / simulated ${spent.toFixed(4)}</span>
              <span className="text-xs text-[#909296]">of ${monthlyBudget.toFixed(2)} monthly quota</span>
            </h2>
            <p className="text-xs text-[#909296] mt-1 flex items-center gap-1.5">
              <Icon className="w-3.5 h-3.5" />
              {descriptionText}
            </p>
          </div>
        </div>

        {/* Detailed stats columns */}
        <div className="flex items-center gap-8 text-right md:ml-auto">
          <div>
            <div className="text-xs text-[#909296]">Recorded / Sim</div>
            <div className="text-sm font-mono text-[#e9ecef] font-semibold mt-0.5">{percentUsed}%</div>
          </div>
          <div className="border-r border-[#2c2e33] h-8" />
          <div>
            <div className="text-xs text-[#909296]">Remaining Limit</div>
            <div className="text-sm font-mono text-[#20c997] font-semibold mt-0.5">${remaining.toFixed(4)}</div>
          </div>
        </div>
      </div>

      {/* Modern Progress Line */}
      <div className="mt-4">
        <div className="w-full bg-[#141517] h-2.5 rounded-full overflow-hidden border border-[#2c2e33]">
          <div
            className={`h-full rounded-full transition-all duration-1000 ${barColorClass}`}
            style={{ width: `${displayPercent}%` }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-[#909296] font-mono mt-1.5 uppercase font-semibold">
          <span>0%</span>
          <span>50%</span>
          <span>85% Warn</span>
          <span>100% Ceil</span>
        </div>
      </div>
    </div>
  );
}
