import React from "react";
import { Activity, Globe } from "lucide-react";
import { SearchUsageType } from "../../types";

interface SearchUsagePanelProps {
  searchData: SearchUsageType;
}

export default function SearchUsagePanel({ searchData }: SearchUsagePanelProps) {
  const { searchCalls, searchCost, status, searchByProvider, searchByAgent } = searchData;
  const providerEntries = Object.entries(searchByProvider).filter(([, calls]) => calls > 0);
  const agentEntries = Object.entries(searchByAgent).filter(([, calls]) => calls > 0);
  const totalProviderCalls = providerEntries.reduce((total, [, calls]) => total + calls, 0);

  return (
    <div id="search-usage-panel" className="mb-6 rounded-lg border border-[#2c2e33] bg-[#1a1b1e] p-5">
      <div className="mb-4 flex items-center justify-between border-b border-[#2c2e33] pb-3.5">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold text-[#e9ecef]">
            <Globe className="h-4 w-4 text-[#20c997]" />
            Search Grounding Costs
          </h3>
          <p className="mt-0.5 font-sans text-[11px] text-[#909296]">
            Additional tracked spend from search and grounding operations.
          </p>
        </div>
      </div>

      <div className="space-y-4">
        <div className="flex items-center justify-between text-xs">
          <span className="font-sans font-semibold text-[#909296]">Total Grounding Spend</span>
          <span className="font-mono text-sm font-bold text-[#e9ecef]">${searchCost.toFixed(4)}</span>
        </div>

        <div className="rounded border border-[#2c2e33] bg-[#141517] p-3">
          <div className="flex items-center gap-2 text-xs">
            <Activity className="h-4 w-4 animate-pulse text-[#20c997]" />
            <span className="font-sans font-bold text-[#e9ecef]">Recorded Search Calls: {searchCalls}</span>
          </div>
          <p className="mt-1 font-sans text-[10px] text-[#909296]">{status}</p>
        </div>

        <div className="space-y-3.5 border-t border-[#2c2e33]/50 pt-3.5 font-sans text-xs">
          <div className="space-y-1.5">
            <div className="flex justify-between text-[11px] font-semibold text-[#909296]">
              <span>Provider Search Share</span>
              <span className="font-mono text-[10px]">{providerEntries.length || 0} active providers</span>
            </div>
            <div className="flex h-2 w-full overflow-hidden rounded-full border border-[#2c2e33] bg-[#141517]">
              {providerEntries.length === 0 ? (
                <div className="h-full w-full bg-[#2c2e33]" title="No search calls recorded" />
              ) : (
                providerEntries.map(([provider, calls], index) => (
                  <div
                    key={provider}
                    className={index % 2 === 0 ? "h-full bg-[#20c997]" : "h-full bg-[#fab005]"}
                    style={{ width: `${(calls / Math.max(1, totalProviderCalls)) * 100}%` }}
                    title={`${provider}: ${calls} calls`}
                  />
                ))
              )}
            </div>
          </div>

          {(providerEntries.length ? providerEntries : [["No provider search", 0] as const]).map(([provider, calls], index) => (
            <div key={provider} className="flex justify-between text-[11px]">
              <span className="flex items-center gap-1.5 font-sans font-semibold text-[#909296]">
                <span className={index % 2 === 0 ? "h-2 w-2 rounded bg-[#20c997]" : "h-2 w-2 rounded bg-[#fab005]"} />
                {provider}
              </span>
              <span className="font-mono font-bold text-[#e9ecef]">{calls} calls</span>
            </div>
          ))}

          {agentEntries.length > 0 && (
            <div className="space-y-1.5 border-t border-[#2c2e33]/40 pt-2">
              <div className="font-mono text-[10px] font-bold uppercase text-[#909296]">Search By Agent</div>
              {agentEntries.map(([agent, calls]) => (
                <div key={agent} className="flex justify-between text-[11px]">
                  <span className="font-sans font-semibold text-[#909296]">{agent}</span>
                  <span className="font-mono font-bold text-[#e9ecef]">{calls} calls</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
