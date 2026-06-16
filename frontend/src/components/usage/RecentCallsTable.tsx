import React, { useState } from "react";
import { RecentCall } from "../../types";
import { ListCollapse, Terminal, AlertTriangle, ShieldCheck } from "lucide-react";

interface RecentCallsTableProps {
  calls: RecentCall[];
}

export default function RecentCallsTable({ calls }: RecentCallsTableProps) {
  const [filterAgent, setFilterAgent] = useState("all");

  const agents = ["all", ...new Set(calls.map((c) => c.agent))];

  const filteredCalls = filterAgent === "all" 
    ? calls 
    : calls.filter((c) => c.agent === filterAgent);

  const formatTokens = (num: number) => {
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toString();
  };

  return (
    <div id="recent-calls-table" className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5 mb-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b border-[#2c2e33] pb-3.5 mb-4 gap-2">
        <div>
          <h3 className="text-sm font-semibold text-[#e9ecef] flex items-center gap-2 font-sans">
            <Terminal className="text-[#20c997] w-4 h-4" />
            High-Frequency Event Logs
          </h3>
          <p className="text-[11px] text-[#909296] mt-0.5 font-sans">
            Realtime sub-agent execution logs and telemetry calls.
          </p>
        </div>

        {/* Local Table Filter */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-[#909296] font-semibold uppercase tracking-wider font-mono">Filter Taskforce:</span>
          <select
            id="agent-filter-select"
            value={filterAgent}
            onChange={(e) => setFilterAgent(e.target.value)}
            className="bg-[#141517] border border-[#2c2e33] text-[#e9ecef] rounded text-[10px] px-2 py-1 focus:ring-1 focus:ring-[#20c997] font-mono outline-none"
          >
            {agents.map((a) => (
              <option key={a} value={a}>
                {a === "all" ? "All Agents" : a}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="max-h-[350px] overflow-y-auto scrollbar-thin scrollbar-thumb-gray-800">
        <table className="w-full text-left text-xs whitespace-nowrap text-sans">
          <thead className="sticky top-0 bg-[#141517]/90 backdrop-blur-sm z-10 text-[#909296] font-semibold border-b border-[#2c2e33] uppercase tracking-wider text-[10px]">
            <tr>
              <th className="py-2 px-3">Call ID</th>
              <th className="py-2 px-2">Timestamp</th>
              <th className="py-2 px-2">Agent Active</th>
              <th className="py-2 px-2">Model &amp; Provider</th>
              <th className="py-2 px-2">Operation</th>
              <th className="py-2 px-2 text-right">Tokens (In/Out)</th>
              <th className="py-2 px-2 text-right">Cost (USD)</th>
              <th className="py-1 px-2 text-right">Latency</th>
              <th className="py-2 px-3 text-center">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#2c2e33]/50">
            {filteredCalls.length === 0 ? (
              <tr>
                <td colSpan={9} className="text-center py-8 text-[#909296] font-sans">
                  No execution logs for the selected agent.
                </td>
              </tr>
            ) : (
              filteredCalls.map((c) => (
                <tr
                  key={c.id}
                  id={`call-row-${c.id}`}
                  className="hover:bg-[#25262b] group transition-colors text-[#e9ecef]"
                >
                  {/* Call ID */}
                  <td className="py-3 px-3 font-mono text-[10px] text-[#20c997] font-bold">
                    #{c.id}
                  </td>

                  {/* Date */}
                  <td className="py-3 px-2 text-[11px] text-[#909296]">
                    {c.time}
                  </td>

                  {/* Agent */}
                  <td className="py-3 px-2 font-bold text-[#e1e2e6]">
                    {c.agent}
                  </td>

                  {/* Model & Provider */}
                  <td className="py-3 px-2">
                    <div className="flex flex-col">
                      <span className="text-[#e1e2e6] font-bold">{c.model}</span>
                      <span className="text-[9px] text-[#909296] font-mono uppercase font-semibold">{c.provider}</span>
                    </div>
                  </td>

                  {/* Request Type */}
                  <td className="py-3 px-2 font-mono text-[10px] text-[#909296]">
                    {c.requestType}
                  </td>

                  {/* Input / Output Tokens */}
                  <td className="py-3 px-2 text-right font-mono text-[#909296] text-[11px]">
                    <span className="text-[#20c997] font-bold">{formatTokens(c.inputTokens)}</span>
                    <span className="text-[#2c2e33] mx-1">/</span>
                    <span className="text-[#fab005] font-bold">{formatTokens(c.outputTokens)}</span>
                  </td>

                  {/* Cost */}
                  <td className="py-3 px-2 text-right font-mono text-[#e9ecef] font-semibold">
                    ${c.cost.toFixed(5)}
                  </td>

                  {/* Latency */}
                  <td className="py-3 px-2 text-right font-mono text-purple-400 text-[11px] font-semibold">
                    {c.latency}ms
                  </td>

                  {/* Status Badging */}
                  <td className="py-3 px-3 text-center">
                    <span
                      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[9px] font-bold border ${
                        c.status === "success"
                          ? "bg-[#20c997]/10 text-[#20c997] border-[#20c997]/20"
                          : "bg-rose-950/10 text-rose-400 border-rose-900/20"
                      }`}
                    >
                      {c.status === "success" ? (
                        <>
                          <ShieldCheck className="w-2.5 h-2.5" />
                          SUCCESS
                        </>
                      ) : (
                        <>
                          <AlertTriangle className="w-2.5 h-2.5 animate-pulse" />
                          FAILED
                        </>
                      )}
                    </span>
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
