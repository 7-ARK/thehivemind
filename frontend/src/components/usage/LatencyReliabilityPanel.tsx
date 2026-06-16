import React from "react";
import { AlertTriangle, ShieldCheck, HelpCircle, Flame } from "lucide-react";

interface LatencyReliabilityPanelProps {
  latencyData: {
    averageLatency: number;
    p95Latency: number;
    slowestModel: string;
    slowestProvider: string;
    successRate: number;
    totalFailedCalls: number;
  };
}

export default function LatencyReliabilityPanel({ latencyData }: LatencyReliabilityPanelProps) {
  const {
    averageLatency,
    p95Latency,
    slowestModel,
    slowestProvider,
    successRate,
    totalFailedCalls,
  } = latencyData;

  const errors = [
    { code: "429 - Rate Limit Exceeded", count: 18, agent: "Coding Agent / OpenRouter" },
    { code: "Timeout Gateway (504)", count: 7, agent: "Research Agent / Search Grounding" },
    { code: "Bad Payload Signature", count: 2, agent: "QA Agent / Content Validation" },
  ];

  return (
    <div id="latency-reliability-panel" className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5 mb-6">
      <div className="flex items-center justify-between border-b border-[#2c2e33] pb-3.5 mb-4">
        <div>
          <h3 className="text-sm font-semibold text-[#e9ecef] flex items-center gap-2">
            <Flame className="w-4 h-4 text-[#20c997]" />
            Reliability &amp; Latency Tracing
          </h3>
          <p className="text-[11px] text-[#909296] mt-0.5 font-sans">
            Identify bottleneck thresholds and catchable model errors.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div className="bg-[#141517] p-3 rounded border border-[#2c2e33]">
          <span className="text-[10px] text-[#909296] font-semibold uppercase tracking-wider font-mono">p95 Latency</span>
          <div className="text-base font-bold font-mono text-purple-400 mt-1">{p95Latency}ms</div>
          <p className="text-[9px] text-[#909296] mt-0.5">Highest latency captured</p>
        </div>
        <div className="bg-[#141517] p-3 rounded border border-[#2c2e33]">
          <span className="text-[10px] text-[#909296] font-semibold uppercase tracking-wider font-mono">Mean RTT</span>
          <div className="text-base font-bold font-mono text-[#20c997] mt-1">{averageLatency}ms</div>
          <p className="text-[9px] text-[#909296] mt-0.5 font-sans">Average roundtrip</p>
        </div>
      </div>

      {/* Extreme traces */}
      <div className="space-y-2.5 text-xs mb-4">
        <div className="flex justify-between items-center text-[11px]">
          <span className="text-[#909296] font-semibold font-sans">Slowest Running Path</span>
          <span className="font-mono text-[#e9ecef] select-all font-semibold break-all text-right max-w-[200px] truncate">
            {slowestModel}
          </span>
        </div>
        <div className="flex justify-between items-center text-[11px]">
          <span className="text-[#909296] font-semibold font-sans">Slowest Provider Connection</span>
          <span className="font-mono text-[#e9ecef] font-bold">{slowestProvider}</span>
        </div>
      </div>

      {/* Exception list logs */}
      <div className="border-t border-[#2c2e33]/50 pt-3.5">
        <div className="text-[11px] font-semibold text-[#909296] mb-2 flex items-center gap-1.5 font-sans uppercase tracking-wider">
          <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
          <span>Intercepted Gateway Warnings ({totalFailedCalls} total)</span>
        </div>
        
        <div className="space-y-2">
          {errors.map((err) => (
            <div key={err.code} id={`rate-limit-code-${err.count}`} className="flex items-center justify-between text-[10px] bg-rose-950/10 border border-rose-900/20 p-2 rounded">
              <div className="font-bold text-rose-400 truncate max-w-[140px] sm:max-w-none">{err.code}</div>
              <div className="text-[#909296] font-mono text-[9px] truncate ml-2">
                {err.agent} · <span className="font-bold text-[#e1e2e6] font-mono">({err.count}x)</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
