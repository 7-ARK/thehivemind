import React, { useState } from "react";
import { RefreshCw, Download, Database, CheckCircle, Sparkles } from "lucide-react";
import { exportUsageCsvUrl } from "../../lib/api";

interface UsageHeaderProps {
  currentRange: string;
  setRange: (range: string) => void;
  onRefresh: () => void;
  onSeedDemo: () => Promise<void>;
  isRefreshing: boolean;
}

export default function UsageHeader({
  currentRange,
  setRange,
  onRefresh,
  onSeedDemo,
  isRefreshing,
}: UsageHeaderProps) {
  const [seeding, setSeeding] = useState(false);
  const [seedSuccess, setSeedSuccess] = useState(false);

  const handleSeed = async () => {
    setSeeding(true);
    setSeedSuccess(false);
    try {
      await onSeedDemo();
      setSeedSuccess(true);
      setTimeout(() => setSeedSuccess(false), 3000);
    } catch (e) {
      console.error(e);
    } finally {
      setSeeding(false);
    }
  };

  const ranges = [
    { label: "Today", value: "today" },
    { label: "7 Days", value: "7d" },
    { label: "30 Days", value: "30d" },
    { label: "This Month", value: "month" },
    { label: "All Time", value: "all" },
  ];

  return (
    <div id="usage-header" className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-[#2c2e33] pb-5 mb-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-[#e9ecef] flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-[#20c997]" />
          Usage &amp; Cost Intelligence
        </h1>
        <p className="text-sm text-[#909296] mt-1 font-sans">
          Observe provider spend allocations, model router effectiveness, and agent execution logs for TheHiveMind.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {/* Range Selector */}
        <div className="flex bg-[#1a1b1e] border border-[#2c2e33] rounded-md p-0.5">
          {ranges.map((r) => (
            <button
              key={r.value}
              id={`range-btn-${r.value}`}
              onClick={() => setRange(r.value)}
              className={`px-3 py-1.5 rounded text-xs font-semibold cursor-pointer transition-colors ${
                currentRange === r.value
                  ? "bg-[#2c2e33] text-[#20c997] border border-[#2c2e33] shadow-sm"
                  : "text-[#909296] hover:text-[#e9ecef]"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          <button
            id="refresh-btn"
            onClick={onRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-[#25262b] hover:bg-[#2c2e33] border border-[#2c2e33] text-[#e9ecef] rounded transition-colors cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin text-[#20c997]" : ""}`} />
            Refresh
          </button>

          <a
            id="export-csv-link"
            href={exportUsageCsvUrl(currentRange)}
            download
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-[#25262b] hover:bg-[#2c2e33] border border-[#2c2e33] text-[#e9ecef] rounded transition-colors cursor-pointer"
          >
            <Download className="w-3.5 h-3.5 text-[#909296]" />
            Export CSV
          </a>

          <button
            id="seed-demo-btn"
            onClick={handleSeed}
            disabled={seeding}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-[#25262b] hover:bg-[#20c997]/5 border border-[#2c2e33] hover:border-[#20c997]/50 text-[#e9ecef] hover:text-[#20c997] rounded transition-all cursor-pointer"
          >
            <Database className={`w-3.5 h-3.5 ${seeding ? "animate-bounce text-[#20c997]" : "text-[#20c997]"}`} />
            {seeding ? "Seeding..." : seedSuccess ? "Seeded!" : "Seed Telemetry"}
            {seedSuccess && <CheckCircle className="w-3 h-3 text-emerald-400" />}
          </button>
        </div>
      </div>
    </div>
  );
}
