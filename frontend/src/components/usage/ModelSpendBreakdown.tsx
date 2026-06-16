import React from "react";
import { ModelUsage } from "../../types";
import { Layers3, Coins, Database, Cpu } from "lucide-react";

interface ModelSpendBreakdownProps {
  models: ModelUsage[];
}

export default function ModelSpendBreakdown({ models }: ModelSpendBreakdownProps) {
  // Always work safely on total cost to prevent divisions by zero
  const totalCost = models.reduce((acc, current) => acc + current.cost, 0);

  // Sort model list descending by spend
  const sortedModels = [...models].sort((a, b) => b.cost - a.cost);

  const formatTokens = (num: number) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(0)}K`;
    return num.toString();
  };

  return (
    <div id="model-spend-breakdown" className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5 mb-6">
      <div className="flex items-center justify-between border-b border-[#2c2e33] pb-3.5 mb-4">
        <div>
          <h3 className="text-sm font-semibold text-[#e9ecef] flex items-center gap-2">
            <Cpu className="w-4 h-4 text-[#20c997]" />
            Model Cost Allocation
          </h3>
          <p className="text-[11px] text-[#909296] mt-0.5 font-sans">
            Identify which orchestrating models capture the bulk of token expenditures.
          </p>
        </div>
        <span className="text-[10px] text-[#909296] font-mono tracking-wider uppercase font-semibold">
          Sorted by cost USD
        </span>
      </div>

      {/* Modern Horizontal Bar Chart representation */}
      <div className="space-y-4 mb-6">
        {sortedModels.map((modelItem) => {
          const pct = totalCost > 0 ? (modelItem.cost / totalCost) * 100 : 0;
          return (
            <div key={modelItem.model} className="space-y-1.5">
              <div className="flex items-center justify-between text-xs my-0.5">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-[#e9ecef]">{modelItem.model}</span>
                  <span className="text-[10px] bg-[#141517] px-2 py-0.5 rounded text-[#909296] border border-[#2c2e33] font-mono">
                    {modelItem.provider}
                  </span>
                  <span className="text-[10px] text-[#909296] italic max-w-[150px] truncate hidden md:inline font-sans">
                    ({modelItem.role})
                  </span>
                </div>
                <div className="flex items-center gap-3 font-mono text-[11px]">
                  <span className="text-[#909296]">${modelItem.cost.toFixed(4)}</span>
                  <span className="font-bold text-[#20c997] w-12 text-right">
                    {pct.toFixed(1)}%
                  </span>
                </div>
              </div>

              {/* Progress Bar with Cyan Segment */}
              <div className="w-full bg-[#141517] h-2 rounded-full overflow-hidden border border-[#2c2e33]/50">
                <div
                  className="bg-[#20c997] h-full rounded-full transition-all duration-500"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Tabular Details */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-[#2c2e33] text-[#909296] font-semibold font-sans uppercase tracking-wider text-[10px]">
              <th className="pb-2.5">Model</th>
              <th className="pb-2.5">Role / Segment</th>
              <th className="pb-2.5 text-right">Calls</th>
              <th className="pb-2.5 text-right">Tokens (In / Out)</th>
              <th className="pb-2.5 text-right">Avg Cost/Call</th>
              <th className="pb-2.5 text-right">Success Rate</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#2c2e33]/50">
            {sortedModels.map((m) => (
              <tr key={m.model} className="text-[#e9ecef] hover:bg-[#25262b] transition-colors">
                <td className="py-2.5 font-bold text-[#e9ecef]">{m.model}</td>
                <td className="py-2.5 text-[#909296] font-sans">{m.role}</td>
                <td className="py-2.5 text-right font-mono text-[#e9ecef] font-semibold">{m.calls}</td>
                <td className="py-2.5 text-right font-mono text-[#909296] text-[11px]">
                  {formatTokens(m.inputTokens)} / {formatTokens(m.outputTokens)}
                </td>
                <td className="py-2.5 text-right font-mono text-[#e9ecef]">${m.averageCostPerCall.toFixed(3)}</td>
                <td className="py-2.5 text-right font-mono">
                  <span className={m.successRate >= 98 ? "text-[#20c997] font-semibold" : m.successRate >= 96 ? "text-[#20c997]" : "text-[#fab005]"}>
                    {m.successRate.toFixed(1)}%
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
