import React from "react";
import { AgentUsage } from "../../types";
import { ShieldAlert, Fingerprint, Layers, Cpu } from "lucide-react";

interface AgentSpendBreakdownProps {
  agents: AgentUsage[];
}

export default function AgentSpendBreakdown({ agents }: AgentSpendBreakdownProps) {
  const totalCost = agents.reduce((acc, current) => acc + current.cost, 0);
  const sortedAgents = [...agents].sort((a, b) => b.cost - a.cost);

  const formatTokens = (num: number) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(2)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(0)}K`;
    return num.toString();
  };

  return (
    <div id="agent-spend-breakdown" className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5 mb-6">
      <div className="flex items-center justify-between border-b border-[#2c2e33] pb-3.5 mb-4">
        <div>
          <h3 className="text-sm font-semibold text-[#e9ecef] flex items-center gap-2">
            <Fingerprint className="w-4 h-4 text-[#20c997]" />
            Agent Role Cost Observation
          </h3>
          <p className="text-[11px] text-[#909296] mt-0.5 font-sans">
            Evaluate cost metrics specifically mapped by Agent delegation, tracking functional workloads.
          </p>
        </div>
        <span className="text-[10px] text-[#909296] font-mono uppercase tracking-wider font-semibold">
          Agent-level governance
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-sans">
          <thead>
            <tr className="border-b border-[#2c2e33] text-[#909296] font-semibold uppercase tracking-wider text-[10px]">
              <th className="pb-3">Agent</th>
              <th className="pb-3 text-right">Cost Share %</th>
              <th className="pb-3 text-right">Calls Assigned</th>
              <th className="pb-3 text-right">Total Tokens</th>
              <th className="pb-3">Primary Model</th>
              <th className="pb-3 text-right">Latency (Mean)</th>
              <th className="pb-3 text-right">Success Rate</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#2c2e33]/50">
            {sortedAgents.map((agentItem) => {
              const pct = totalCost > 0 ? (agentItem.cost / totalCost) * 100 : 0;
              return (
                <tr key={agentItem.agent} className="text-[#e9ecef] hover:bg-[#25262b] transition-colors">
                  {/* Name */}
                  <td className="py-3">
                    <div className="flex items-center gap-2">
                      <div className="w-1.5 h-1.5 bg-[#20c997] rounded-full shrink-0 animate-pulse" />
                      <span className="font-bold text-[#e9ecef]">{agentItem.agent}</span>
                    </div>
                  </td>

                  {/* Percentage with Micro progress bar */}
                  <td className="py-3 text-right">
                    <div className="inline-flex items-center gap-2">
                      <span className="font-mono font-bold text-[#e1e2e6]">${agentItem.cost.toFixed(4)}</span>
                      <span className="font-mono text-[#20c997] font-semibold text-[10px]">({pct.toFixed(1)}%)</span>
                      <div className="w-12 bg-[#141517] h-1.5 rounded-full overflow-hidden border border-[#2c2e33] hidden sm:inline-block">
                        <div
                          className="bg-[#20c997] h-full rounded-full"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  </td>

                  {/* Calls */}
                  <td className="py-3 text-right font-mono text-[#e9ecef] font-semibold">
                    {agentItem.calls}
                  </td>

                  {/* Tokens */}
                  <td className="py-3 text-right font-mono text-[#909296] text-[11px]">
                    {formatTokens(agentItem.tokens)}
                  </td>

                  {/* Primary Model */}
                  <td className="py-3 font-sans">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs text-[#e9ecef] font-medium">{agentItem.primaryModel}</span>
                      <span className="text-[9px] bg-[#141517] text-[#909296] font-mono border border-[#2c2e33] px-1 py-0.2 rounded shrink-0">
                        {agentItem.provider}
                      </span>
                    </div>
                  </td>

                  {/* Latency */}
                  <td className="py-3 text-right font-mono text-purple-400 text-[11px] font-semibold">
                    {agentItem.averageLatency}ms
                  </td>

                  {/* Success Rate */}
                  <td className="py-3 text-right font-mono">
                    <span className={agentItem.successRate >= 98 ? "text-[#20c997] font-bold" : agentItem.successRate >= 96 ? "text-[#20c997]" : "text-[#fab005]"}>
                      {agentItem.successRate.toFixed(1)}%
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
