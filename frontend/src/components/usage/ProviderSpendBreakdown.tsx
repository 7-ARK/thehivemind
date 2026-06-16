import React, { useState } from "react";
import { ProviderUsage } from "../../types";
import { Server, HelpCircle, ArrowUpRight, Cpu } from "lucide-react";

interface ProviderSpendBreakdownProps {
  providers: ProviderUsage[];
}

export default function ProviderSpendBreakdown({ providers }: ProviderSpendBreakdownProps) {
  const [hoveredProvider, setHoveredProvider] = useState<string | null>(null);
  
  const totalCost = providers.reduce((acc, current) => acc + current.cost, 0);
  const totalCalls = providers.reduce((acc, current) => acc + current.calls, 0);

  const formatTokens = (num: number) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(2)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toString();
  };

  const getProviderColor = (pName: string) => {
    const name = pName.toLowerCase();
    if (name.includes("openai")) return "#20c997"; // Mint Green
    if (name.includes("gemini")) return "#845ef7"; // Soft Purple
    return "#fab005"; // Cozy Amber
  };

  // Circular Donut calculations
  const radius = 50;
  const circumference = 2 * Math.PI * radius; // ~314.159

  let accumulatedDash = 0;
  const slices = providers.map((p) => {
    const pct = totalCost > 0 ? (p.cost / totalCost) * 100 : 0;
    const strokeDash = (pct / 100) * circumference;
    const strokeOffset = accumulatedDash;
    accumulatedDash += strokeDash;
    
    return {
      ...p,
      pct,
      strokeDash,
      strokeOffset,
      color: getProviderColor(p.provider),
    };
  });

  // Current active data for center of Donut
  const activeData = hoveredProvider 
    ? slices.find(s => s.provider === hoveredProvider) 
    : null;

  return (
    <div id="provider-spend-breakdown" className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5 mb-6">
      <div className="flex items-center justify-between border-b border-[#2c2e33] pb-3.5 mb-5">
        <div>
          <h3 className="text-sm font-semibold text-[#e9ecef] flex items-center gap-2">
            <Server className="w-4 h-4 text-[#20c997]" />
            Provider Allocation Benchmarks
          </h3>
          <p className="text-[11px] text-[#909296] mt-0.5 font-sans">
            Tactile multi-provider routing distribution metrics.
          </p>
        </div>
        <span className="text-[9px] bg-[#25262b] border border-[#2c2e33] text-[#20c997] font-mono px-2 py-0.5 rounded uppercase font-semibold">
          Live Interactive Rings
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
        {/* Interactive SVG Circular Donut Chart */}
        <div className="lg:col-span-5 flex flex-col items-center justify-center p-3 bg-[#141517] border border-[#2c2e33] rounded-lg relative min-h-[220px]">
          <span className="absolute top-2.5 left-3 text-[9px] text-[#909296] font-mono uppercase tracking-wider font-semibold">
            Allocation Share Ring
          </span>

          <div className="relative w-40 h-40">
            {/* SVG Donut Container */}
            <svg viewBox="0 0 120 120" className="w-full h-full -rotate-90 origin-center">
              {/* Background trace ring */}
              <circle
                cx="60"
                cy="60"
                r={radius}
                fill="none"
                stroke="#25262b"
                strokeWidth="11"
              />
              {/* Colored Segments */}
              {slices.map((slice) => {
                const isHovered = hoveredProvider === slice.provider;
                return (
                  <circle
                    key={slice.provider}
                    cx="60"
                    cy="60"
                    r={radius}
                    fill="none"
                    stroke={slice.color}
                    strokeWidth={isHovered ? "14" : "11"}
                    strokeDasharray={`${slice.strokeDash} ${circumference}`}
                    strokeDashoffset={-slice.strokeOffset}
                    strokeLinecap={slice.pct > 3 ? "round" : "butt"}
                    className="transition-all duration-300 cursor-pointer"
                    onMouseEnter={() => setHoveredProvider(slice.provider)}
                    onMouseLeave={() => setHoveredProvider(null)}
                    style={{
                      opacity: hoveredProvider && !isHovered ? 0.35 : 1,
                      transform: isHovered ? "scale(1.02)" : "scale(1)",
                      transformOrigin: "center",
                    }}
                  />
                );
              })}
            </svg>

            {/* Tactile readout display in the exact center of Donut */}
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none text-center px-4">
              {activeData ? (
                <div className="fade-in space-y-0.5">
                  <span className="text-[9px] uppercase tracking-wider font-mono font-bold" style={{ color: activeData.color }}>
                    {activeData.provider}
                  </span>
                  <div className="text-sm font-extrabold font-mono text-[#e9ecef]">
                    {activeData.pct.toFixed(1)}%
                  </div>
                  <div className="text-[9px] text-[#909296]">
                    ${activeData.cost.toFixed(2)}
                  </div>
                </div>
              ) : (
                <div className="fade-in space-y-0.5">
                  <span className="text-[9px] text-[#909296] uppercase tracking-wider font-mono font-semibold">
                    Total Budget
                  </span>
                  <div className="text-sm font-extrabold font-mono text-[#e9ecef]">
                    ${totalCost.toFixed(2)}
                  </div>
                  <div className="text-[8px] text-[#20c997] font-mono">
                    {totalCalls} calls
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="flex gap-4 mt-3 justify-center">
            {slices.map((slice) => (
              <div
                key={slice.provider}
                className="flex items-center gap-1.5 cursor-pointer"
                onMouseEnter={() => setHoveredProvider(slice.provider)}
                onMouseLeave={() => setHoveredProvider(null)}
              >
                <span className="w-2 h-2 rounded" style={{ backgroundColor: slice.color }} />
                <span className={`text-[10px] font-mono font-bold transition-colors ${hoveredProvider === slice.provider ? "text-[#e9ecef]" : "text-[#909296]"}`}>
                  {slice.provider}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Detailed stats cards side */}
        <div className="lg:col-span-7 space-y-3">
          {slices.map((p) => {
            const isHovered = hoveredProvider === p.provider;
            return (
              <div
                key={p.provider}
                id={`provider-hover-card-${p.provider}`}
                onMouseEnter={() => setHoveredProvider(p.provider)}
                onMouseLeave={() => setHoveredProvider(null)}
                className={`transition-all duration-300 p-3.5 rounded border ${
                  isHovered 
                    ? "bg-[#25262b] border-[#20c997] shadow-md translate-x-1" 
                    : "bg-[#141517] border-[#2c2e33] hover:border-[#909296]/30"
                }`}
              >
                <div className="flex justify-between items-center">
                  <div className="flex items-center gap-2">
                    <span 
                      className="w-1.5 h-3 rounded-full transition-all duration-300" 
                      style={{ 
                        backgroundColor: p.color,
                        height: isHovered ? "16px" : "12px"
                      }} 
                    />
                    <h4 className="text-xs font-extrabold text-[#e9ecef] tracking-wide uppercase font-sans">
                      {p.provider}
                    </h4>
                  </div>
                  <div className="text-right flex items-center gap-2 font-mono">
                    <span className="text-xs font-extrabold text-[#e9ecef]">${p.cost.toFixed(4)}</span>
                    <span className="text-[10px] px-1.5 py-0.2 bg-[#1a1b1e] text-[#909296] border border-[#2c2e33] rounded font-semibold">
                      {p.pct.toFixed(1)}%
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-4 gap-2 mt-3 pt-2.5 border-t border-[#2c2e33]/60 text-[9px]">
                  <div>
                    <span className="text-[#909296] block uppercase tracking-wider font-mono">Calls</span>
                    <span className="text-[#e9ecef] font-mono font-bold text-[10px]">{p.calls}</span>
                  </div>
                  <div>
                    <span className="text-[#909296] block uppercase tracking-wider font-mono">Tokens</span>
                    <span className="text-[#e9ecef] font-mono font-bold text-[10px]">{formatTokens(p.tokens)}</span>
                  </div>
                  <div>
                    <span className="text-[#909296] block uppercase tracking-wider font-mono">Latency</span>
                    <span className="text-[#845ef7] font-mono font-bold text-[10px]">{p.averageLatency}ms</span>
                  </div>
                  <div>
                    <span className="text-[#909296] block uppercase tracking-wider font-mono">Precision</span>
                    <span className="text-[#20c997] font-mono font-bold text-[10px]">{p.successRate}%</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

