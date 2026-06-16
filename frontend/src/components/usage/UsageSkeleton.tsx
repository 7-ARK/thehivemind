import React from "react";

export default function UsageSkeleton() {
  return (
    <div id="usage-skeletons" className="space-y-6">
      {/* Budget Guardrail Skeleton */}
      <div className="bg-gray-900/40 border border-gray-800 rounded-xl p-5 animate-pulse relative overflow-hidden">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-gray-800 rounded-lg" />
          <div className="space-y-2 flex-1">
            <div className="h-3 bg-gray-800 rounded w-1/4" />
            <div className="h-5 bg-gray-800 rounded w-1/3" />
          </div>
          <div className="w-24 h-8 bg-gray-800 rounded" />
        </div>
        <div className="mt-4 h-3 bg-gray-800 rounded-full w-full" />
      </div>

      {/* KPI Grid Skeleton */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, idx) => (
          <div key={idx} className="bg-gray-900/40 border border-gray-800 rounded-xl p-4 space-y-3 animate-pulse">
            <div className="flex justify-between items-center">
              <div className="h-3 bg-gray-800 rounded w-1/2" />
              <div className="w-6 h-6 bg-gray-800 rounded" />
            </div>
            <div className="h-6 bg-gray-800 rounded w-2/3" />
            <div className="h-2.5 bg-gray-800 rounded w-3/4" />
          </div>
        ))}
      </div>

      {/* Columns Skeletons */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-gray-900/40 border border-gray-800 rounded-xl p-5 h-80 animate-pulse">
            <div className="h-4 bg-gray-800 rounded w-1/3 mb-4" />
            <div className="space-y-4">
              <div className="h-8 bg-gray-800 rounded" />
              <div className="h-8 bg-gray-800 rounded" />
              <div className="h-8 bg-gray-800 rounded" />
            </div>
          </div>
        </div>
        <div className="space-y-6">
          <div className="bg-gray-900/40 border border-gray-800 rounded-xl p-5 h-81 animate-pulse">
            <div className="h-4 bg-gray-800 rounded w-1/2 mb-4" />
            <div className="h-full bg-gray-800/20 rounded" />
          </div>
        </div>
      </div>
    </div>
  );
}
