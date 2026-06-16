import React from "react";
import { ExpensiveRun } from "../../types";
import { ListRestart, ShieldAlert, Cpu, Network } from "lucide-react";

interface ExpensiveRunsTableProps {
  runs: ExpensiveRun[];
}

export default function ExpensiveRunsTable({ runs }: ExpensiveRunsTableProps) {
  const formatTokens = (num: number) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(2)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(0)}K`;
    return num.toString();
  };

  return (
    <div id="expensive-runs-table" className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5 mb-6">
      <div className="flex items-center justify-between border-b border-[#2c2e33] pb-3.5 mb-4">
        <div>
          <h3 className="text-sm font-semibold text-[#e9ecef] flex items-center gap-2">
            <Network className="text-[#20c997] w-4 h-4" />
            Top Cumulative Orchestration Runs
          </h3>
          <p className="text-[11px] text-[#909296] mt-0.5 font-sans">
            Observability on compound tasks requiring multi-agent sequences.
          </p>
        </div>
      </div>

      <div className="overflow-x-auto select-none">
        <table className="w-full text-left text-xs whitespace-nowrap text-sans">
          <thead>
            <tr className="border-b border-[#2c2e33] text-[#909296] font-semibold uppercase tracking-wider text-[10px]">
              <th className="py-2.5 px-2">Run ID</th>
              <th className="py-2.5 px-2">Orchestration Prompt Command</th>
              <th className="py-2.5 px-2 text-right">Cost (USD)</th>
              <th className="py-2.5 px-2 text-right">Total Tokens</th>
              <th className="py-2.5 px-2">Active Infrastructure Platforms</th>
              <th className="py-2.5 px-3 text-right">Steps Run</th>
              <th className="py-2.5 px-2 text-right">Failures</th>
              <th className="py-2.5 px-2 text-right">Execution Date</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#2c2e33]/50">
            {runs.length === 0 ? (
              <tr>
                <td colSpan={8} className="text-center py-6 text-[#909296] font-sans">
                  No multiagent execution traces created yet.
                </td>
              </tr>
            ) : (
              runs.map((r) => (
                <tr key={r.id} className="hover:bg-[#25262b] transition-colors text-[#e9ecef]">
                  <td className="py-3.5 px-2 font-mono text-[11px] font-bold text-[#20c997]">
                    #{r.id}
                  </td>
                  <td className="py-3.5 px-2 font-semibold text-[#e9ecef] truncate max-w-[220px]" title={r.title}>
                    {r.title}
                  </td>
                  <td className="py-3.5 px-2 text-right font-mono font-bold text-[#fab005]">
                    ${r.cost.toFixed(4)}
                  </td>
                  <td className="py-3.5 px-2 text-right font-mono text-[#909296] font-semibold">
                    {formatTokens(r.totalTokens)}
                  </td>
                  {/* Providers badging list */}
                  <td className="py-3.5 px-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      {r.providers.map((p) => (
                        <span key={p} className="text-[9px] bg-[#141517] font-mono border border-[#2c2e33] px-1.5 py-0.2 rounded text-[#909296] font-semibold uppercase">
                          {p}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="py-3.5 px-3 text-right font-mono text-[#e9ecef] font-bold">
                    {r.callCount}
                  </td>
                  <td className="py-3.5 px-2 text-right font-mono">
                    {r.failedCalls > 0 ? (
                      <span className="text-rose-400 font-bold">{r.failedCalls}</span>
                    ) : (
                      <span className="text-gray-600">0</span>
                    )}
                  </td>
                  <td className="py-3.5 px-2 text-right font-mono text-[11px] text-[#909296]">
                    {r.timestamp}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
