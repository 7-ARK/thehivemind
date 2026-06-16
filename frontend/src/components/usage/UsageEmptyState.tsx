import React from "react";
import { Sparkles, Database, RotateCw } from "lucide-react";

interface UsageEmptyStateProps {
  onSeed: () => void;
  onRefresh: () => void;
  isSeeding: boolean;
}

export default function UsageEmptyState({ onSeed, onRefresh, isSeeding }: UsageEmptyStateProps) {
  return (
    <div id="usage-empty-state" className="bg-gray-900/60 border border-gray-800 rounded-xl p-8 py-14 text-center max-w-xl mx-auto my-12">
      <div className="w-12 h-12 bg-gray-950 border border-gray-800/80 text-cyan-400 rounded-full flex items-center justify-center mx-auto mb-4">
        <Sparkles className="w-6 h-6 animate-pulse" />
      </div>

      <h3 className="text-base font-semibold text-gray-200">No Observability Data Found</h3>
      <p className="text-xs text-gray-400 max-w-sm mx-auto mt-2 leading-relaxed">
        Mock or live provider logs have not accumulated yet. Seed high-frequency analytical data to explore model governance.
      </p>

      <div className="flex items-center justify-center gap-3 mt-6">
        <button
          onClick={onSeed}
          disabled={isSeeding}
          className="flex items-center gap-2 px-4 py-2 text-xs bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg font-medium transition-all active:scale-95 cursor-pointer"
        >
          <Database className="w-4 h-4" />
          {isSeeding ? "Seeding..." : "Seed Demo Telemetry"}
        </button>

        <button
          onClick={onRefresh}
          className="flex items-center gap-2 px-4 py-2 text-xs bg-gray-950 hover:bg-gray-900 border border-gray-800 text-gray-300 rounded-lg font-medium transition-all active:scale-95 cursor-pointer"
        >
          <RotateCw className="w-4 h-4" />
          Refresh
        </button>
      </div>
    </div>
  );
}
