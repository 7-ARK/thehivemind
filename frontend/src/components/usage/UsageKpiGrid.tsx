import React from "react";
import { UsageSummary } from "../../types";
import {
  Coins,
  Activity,
  Zap,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Layers,
  Globe,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

interface UsageKpiGridProps {
  summary: UsageSummary;
}

export default function UsageKpiGrid({ summary }: UsageKpiGridProps) {
  const formatTokens = (num: number) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(2)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toString();
  };

  const kpis = [
    {
      label: "Accrued Spend",
      value: `$${summary.totalCost.toFixed(4)}`,
      desc: "Cumulative routing costs",
      trend: "5.2% under forecast",
      trendUp: false,
      color: "text-[#fab005] border-[#2c2e33] bg-[#fab005]/5",
      icon: <Coins className="w-4 h-4 text-[#fab005]" />,
    },
    {
      label: "Total Executions",
      value: summary.totalCalls.toLocaleString(),
      desc: "Summed agent calls completed",
      trend: "+12.4% vs last cycle",
      trendUp: true,
      color: "text-[#20c997] border-[#2c2e33] bg-[#20c997]/5",
      icon: <Activity className="w-4 h-4 text-[#20c997]" />,
    },
    {
      label: "Optimized Tokens",
      value: formatTokens(summary.totalTokens),
      desc: "Input + completion payload",
      trend: `${formatTokens(summary.cachedTokenSavings)} cached`,
      trendUp: true,
      color: "text-[#20c997] border-[#2c2e33] bg-[#20c997]/5",
      icon: <Zap className="w-4 h-4 text-[#20c997]" />,
    },
    {
      label: "Selector Precision",
      value: `${summary.successRate.toFixed(1)}%`,
      desc: "Successful routing completions",
      trend: `${summary.failedCalls} failed calls`,
      trendUp: true,
      color: "text-[#20c997] border-[#2c2e33] bg-[#20c997]/5",
      icon: <CheckCircle2 className="w-4 h-4 text-[#20c997]" />,
    },
    {
      label: "Mean Latency",
      value: `${summary.averageLatency}ms`,
      desc: "Weighted model response time",
      trend: "Backend measured",
      trendUp: false,
      color: "text-purple-400 border-purple-950 bg-purple-500/2",
      icon: <Clock className="w-4 h-4 text-purple-400" />,
    },
    {
      label: "Unresolved Failures",
      value: summary.failedCalls.toString(),
      desc: "API errors caught & retried",
      trend: summary.failedCalls > 0 ? "Inspect recent logs" : "No failures recorded",
      trendUp: true,
      color: "text-rose-400 border-rose-950 bg-rose-500/2",
      icon: <AlertTriangle className="w-4 h-4 text-rose-400" />,
    },
    {
      label: "Cache Memory Offset",
      value: formatTokens(summary.cachedTokenSavings),
      desc: "Saved by context replication",
      trend: `$${summary.cachedCostSavings.toFixed(4)} saved`,
      trendUp: true,
      color: "text-[#20c997] border-[#2c2e33] bg-[#20c997]/5",
      icon: <Layers className="w-4 h-4 text-[#20c997]" />,
    },
    {
      label: "Search & Grounding",
      value: `$${summary.searchCost.toFixed(2)}`,
      desc: `Over ${summary.searchCalls} web lookups`,
      trend: "Backend recorded",
      trendUp: false,
      color: "text-[#fab005] border-[#2c2e33] bg-[#fab005]/5",
      icon: <Globe className="w-4 h-4 text-[#fab005]" />,
    },
  ];

  return (
    <div id="usage-kpis-grid" className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {kpis.map((kpi, idx) => (
        <div
          key={kpi.label}
          id={`kpi-card-${idx}`}
          className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4 transition-all hover:border-[#20c997]/50 hover:bg-[#25262b] relative overflow-hidden group"
        >
          {/* Decorative faint glow */}
          <div className="absolute right-0 top-0 -translate-x-4 translate-y-4 w-12 h-12 bg-gray-800/10 rounded-full group-hover:bg-[#20c997]/2 transition-colors blur-xl pointer-events-none" />

          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-[#909296] font-semibold font-sans tracking-tight truncate">
              {kpi.label}
            </span>
            <div className="p-1 px-1.5 shrink-0 bg-[#141517] border border-[#2c2e33] rounded">
              {kpi.icon}
            </div>
          </div>

          <div className="text-lg font-semibold text-[#e9ecef] font-mono tracking-tight mt-2.5">
            {kpi.value}
          </div>

          <p className="text-[10px] text-[#909296] tracking-tight mt-1 truncate">{kpi.desc}</p>

          <div className="border-t border-[#2c2e33]/50 my-2.5" />

          <div className="flex items-center gap-1 text-[9px] font-mono text-[#909296]">
            {kpi.trendUp ? (
              <TrendingUp className="w-2.5 h-2.5 text-[#20c997] shrink-0" />
            ) : (
              <TrendingDown className="w-2.5 h-2.5 text-[#fab005] shrink-0" />
            )}
            <span className="truncate">{kpi.trend}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
