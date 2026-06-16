import React, { useState } from "react";
import { TokenBreakdownType } from "../../types";
import { Layers, HardDrive, Info, ArrowUpRight } from "lucide-react";

interface TokenBreakdownProps {
  tokens: TokenBreakdownType;
}

export default function TokenBreakdown({ tokens }: TokenBreakdownProps) {
  const [activeRing, setActiveRing] = useState<"input" | "output" | "reasoning" | null>(null);
  
  const { inputTokens, outputTokens, cachedTokens, reasoningTokens } = tokens;
  const total = inputTokens + outputTokens;

  const pctInput = total > 0 ? (inputTokens / total) * 100 : 0;
  const pctOutput = total > 0 ? (outputTokens / total) * 100 : 0;
  const pctReasoning = total > 0 ? (reasoningTokens / total) * 100 : 0;

  const formatTokens = (num: number) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(2)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toString();
  };

  // Concentric ring parameters
  const rings = [
    {
      id: "input" as const,
      name: "Input Context",
      pct: pctInput,
      color: "#20c997", // Mint-emerald
      radius: 40,
      circumference: 2 * Math.PI * 40, // ~251.3
      val: formatTokens(inputTokens),
    },
    {
      id: "output" as const,
      name: "Generated Output",
      pct: pctOutput,
      color: "#fab005", // Amber
      radius: 30,
      circumference: 2 * Math.PI * 30, // ~188.5
      val: formatTokens(outputTokens),
    },
    {
      id: "reasoning" as const,
      name: "Reasoning Pass",
      pct: pctReasoning,
      color: "#a29bfe", // Purple
      radius: 20,
      circumference: 2 * Math.PI * 20, // ~125.6
      val: formatTokens(reasoningTokens),
    }
  ];

  return (
    <div id="token-breakdown" className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5 mb-6">
      <div className="flex items-center justify-between border-b border-[#2c2e33] pb-3.5 mb-4">
        <div>
          <h3 className="text-sm font-semibold text-[#e9ecef] flex items-center gap-2">
            <Layers className="w-4 h-4 text-[#20c997]" />
            Payload Token Analysis
          </h3>
          <p className="text-[11px] text-[#909296] mt-0.5 font-sans">
            Concentric distribution of logic payloads and completions.
          </p>
        </div>
      </div>

      <div className="space-y-5">
        {/* Total Tokens Readout */}
        <div className="flex justify-between items-center bg-[#141517] p-2.5 rounded border border-[#2c2e33]/60 text-xs">
          <span className="text-[#909296] font-mono uppercase tracking-wider text-[10px] font-semibold">Total Swarm Bandwidth</span>
          <span className="font-bold text-[#20c997] font-mono text-sm">{formatTokens(total)}</span>
        </div>

        {/* Concentric Circle Radial Gauge Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-12 gap-4 items-center">
          {/* Radial concentric circle graphics */}
          <div className="sm:col-span-5 flex items-center justify-center p-2 relative h-[120px]">
            <svg viewBox="0 0 100 100" className="w-[110px] h-[110px] -rotate-90 origin-center">
              {rings.map((ring) => {
                const isHovered = activeRing === ring.id;
                const dash = (ring.pct / 100) * ring.circumference;
                return (
                  <g key={ring.id} className="transition-all duration-300">
                    {/* Ghost track background */}
                    <circle
                      cx="50"
                      cy="50"
                      r={ring.radius}
                      fill="none"
                      stroke="#25262b"
                      strokeWidth="5"
                    />
                    {/* Active foreground arc segment */}
                    <circle
                      cx="50"
                      cy="50"
                      r={ring.radius}
                      fill="none"
                      stroke={ring.color}
                      strokeWidth={isHovered ? "7" : "5"}
                      strokeDasharray={`${dash} ${ring.circumference}`}
                      strokeLinecap="round"
                      className="cursor-pointer transition-all duration-300"
                      onMouseEnter={() => setActiveRing(ring.id)}
                      onMouseLeave={() => setActiveRing(null)}
                      style={{
                        opacity: activeRing && !isHovered ? 0.35 : 1,
                      }}
                    />
                  </g>
                );
              })}
            </svg>
            
            {/* Tiny center label inside the ring stack */}
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none text-center">
              {activeRing ? (
                <div className="fade-in">
                  <span className="text-[7px] uppercase tracking-wider font-mono font-bold" style={{ color: rings.find(r => r.id === activeRing)?.color }}>
                    {activeRing}
                  </span>
                  <div className="text-[10px] font-extrabold text-[#e9ecef] font-mono">
                    {rings.find(r => r.id === activeRing)?.pct.toFixed(0)}%
                  </div>
                </div>
              ) : (
                <div className="fade-in text-center">
                  <Layers className="w-3.5 h-3.5 text-[#20c997] mx-auto opacity-75" />
                  <span className="text-[7.5px] text-[#909296] font-mono uppercase font-bold block mt-0.5">Payload</span>
                </div>
              )}
            </div>
          </div>

          {/* Right Text details and legend */}
          <div className="sm:col-span-7 space-y-2">
            {rings.map((r) => {
              const isHovered = activeRing === r.id;
              return (
                <div
                  key={r.id}
                  onMouseEnter={() => setActiveRing(r.id)}
                  onMouseLeave={() => setActiveRing(null)}
                  className={`p-1.5 px-2.5 rounded transition-all duration-200 border cursor-default flex items-center justify-between ${
                    isHovered 
                      ? "bg-[#25262b] border-[#2c2e33]" 
                      : "bg-transparent border-transparent"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded shrink-0" style={{ backgroundColor: r.color }} />
                    <span className="text-xs font-semibold text-[#c1c2c5] font-sans truncate">{r.name}</span>
                  </div>
                  <div className="text-right font-mono text-[11px] font-bold text-[#e9ecef]">
                    {r.val}
                    <span className="text-[9px] text-[#909296] ml-1 font-normal">({r.pct.toFixed(0)}%)</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="border-t border-[#2c2e33]/50 pt-3.5 space-y-3.5 text-xs">
          {/* Cached Token Savings details */}
          <div className="flex justify-between items-start">
            <div>
              <div className="text-[#e9ecef] font-semibold flex items-center gap-1.5 font-sans">
                <HardDrive className="w-3.5 h-3.5 text-[#20c997]" />
                Swarm Cache Reductions
              </div>
              <p className="text-[10px] text-[#909296] mt-0.5 font-sans">Repeated prompt blocks served from memory</p>
            </div>
            <div className="text-right">
              <div className="font-mono text-[#20c997] font-bold">{formatTokens(cachedTokens)}</div>
              <div className="text-[9px] text-[#20c997] font-mono bg-[#20c997]/10 px-1 py-0.2 rounded mt-0.5 inline-block font-bold">~14.8% bytes saved</div>
            </div>
          </div>

          {/* Reasoning tokens */}
          <div className="flex justify-between items-start">
            <div>
              <div className="text-[#e9ecef] font-semibold flex items-center gap-1.5 font-sans">
                <Info className="w-3.5 h-3.5 text-[#a29bfe]" />
                Reasoning Token Passes
              </div>
              <p className="text-[10px] text-[#909296] mt-0.5 font-sans">Advanced sequence passes & planning tokens</p>
            </div>
            <div className="text-right">
              <div className="font-mono text-[#a29bfe] font-bold">{formatTokens(reasoningTokens)}</div>
              <div className="text-[9px] text-[#a29bfe] font-mono bg-[#a29bfe]/10 px-1 py-0.2 rounded mt-0.5 inline-block font-bold">12% total volume</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

