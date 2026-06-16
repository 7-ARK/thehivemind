import React, { useState } from "react";
import { UsageTimeSeriesPoint } from "../../types";
import { TrendingUp, Clock, CalendarDays, LineChart, BarChart2 } from "lucide-react";

interface UsageTimeSeriesProps {
  timeSeries: UsageTimeSeriesPoint[];
}

export default function UsageTimeSeries({ timeSeries }: UsageTimeSeriesProps) {
  const [metric, setMetric] = useState<"cost" | "calls">("cost");
  const [chartStyle, setChartStyle] = useState<"curve" | "bars">("curve");
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  if (!timeSeries || timeSeries.length === 0) {
    return (
      <div className="bg-gray-900/60 border border-gray-800 rounded-xl p-5 mb-6 h-56 flex items-center justify-center text-gray-400">
        No timeseries data to render.
      </div>
    );
  }

  // Get values based on selected metric
  const values = timeSeries.map((p) => (metric === "cost" ? p.cost : p.calls));
  const maxValue = Math.max(...values, 1);
  const minValue = Math.min(...values, 0);

  // SVG dimensions
  const width = 600;
  const height = 150;
  const paddingLeft = 45;
  const paddingRight = 10;
  const paddingTop = 20;
  const paddingBottom = 22;

  const chartWidth = width - paddingLeft - paddingRight;
  const chartHeight = height - paddingTop - paddingBottom;
  const baselineY = paddingTop + chartHeight;

  // Calculate coordinates for SVG points
  const points = timeSeries.map((p, idx) => {
    const xRatio = timeSeries.length === 1 ? 0.5 : idx / (timeSeries.length - 1);
    const x = paddingLeft + xRatio * chartWidth;
    const value = metric === "cost" ? p.cost : p.calls;
    // Map value to coordinate (Y decreases as value increases in SVG)
    const y = paddingTop + chartHeight - ((value - minValue) / (maxValue - minValue)) * chartHeight;
    return { x, y, ...p };
  });

  // Construct SVG path string for the line
  const linePath = points.length > 0 
    ? `M ${points[0].x} ${points[0].y} ` + points.slice(1).map((p) => `L ${p.x} ${p.y}`).join(" ")
    : "";

  // Area path string (goes down to baseline and closes)
  const areaPath = linePath 
    ? `${linePath} L ${points[points.length - 1].x} ${baselineY} L ${points[0].x} ${baselineY} Z`
    : "";

  // Grid lines
  const gridLinesY = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
    return paddingTop + ratio * chartHeight;
  });

  const activeColor = metric === "cost" ? "#fab005" : "#20c997";

  return (
    <div id="usage-timeseries" className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5 mb-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b border-[#2c2e33] pb-3.5 mb-4 gap-3">
        <div>
          <h3 className="text-sm font-semibold text-[#e9ecef] flex items-center gap-2 font-sans">
            <TrendingUp className="text-[#20c997] w-4 h-4" />
            Performance Trend Analytics
          </h3>
          <p className="text-[11px] text-[#909296] mt-0.5 font-sans">
            Hourly and daily aggregated telemetry traces.
          </p>
        </div>

        {/* Style & Metric control panel */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Chart visual layout switcher */}
          <div className="flex bg-[#141517] border border-[#2c2e33] p-0.5 rounded-md">
            <button
              id="chart-style-curve-btn"
              onClick={() => setChartStyle("curve")}
              className={`p-1 px-2 rounded text-[10px] cursor-pointer transition-all flex items-center gap-1 ${
                chartStyle === "curve" 
                  ? "bg-[#2c2e33] text-[#20c997] font-bold" 
                  : "text-[#909296] hover:text-[#e9ecef]"
              }`}
              title="Continuous Spline Area"
            >
              <LineChart className="w-3 h-3" />
              <span>Spline</span>
            </button>
            <button
              id="chart-style-bars-btn"
              onClick={() => setChartStyle("bars")}
              className={`p-1 px-2 rounded text-[10px] cursor-pointer transition-all flex items-center gap-1 ${
                chartStyle === "bars" 
                  ? "bg-[#2c2e33] text-[#20c997] font-bold" 
                  : "text-[#909296] hover:text-[#e9ecef]"
              }`}
              title="Discrete Pillars"
            >
              <BarChart2 className="w-3 h-3" />
              <span>Columns</span>
            </button>
          </div>

          {/* Metric Selector */}
          <div className="flex bg-[#141517] border border-[#2c2e33] p-0.5 rounded-md shrink-0">
            <button
              id="metric-cost-btn"
              onClick={() => { setMetric("cost"); setHoveredIndex(null); }}
              className={`px-3 py-1 rounded text-[10px] font-mono cursor-pointer transition-all ${
                metric === "cost" ? "bg-[#2c2e33] text-[#fab005] font-bold" : "text-[#909296] hover:text-[#e9ecef]"
              }`}
            >
              Cost (USD)
            </button>
            <button
              id="metric-calls-btn"
              onClick={() => { setMetric("calls"); setHoveredIndex(null); }}
              className={`px-3 py-1 rounded text-[10px] font-mono cursor-pointer transition-all ${
                metric === "calls" ? "bg-[#2c2e33] text-[#20c997] font-bold" : "text-[#909296] hover:text-[#e9ecef]"
              }`}
            >
              Calls
            </button>
          </div>
        </div>
      </div>

      <div className="relative pt-2">
        {/* Responsive custom clean SVG */}
        <div className="w-full overflow-hidden">
          <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto text-gray-800 overflow-visible" alt="Usage Timeseries Graph">
            {/* Grid Line render */}
            {gridLinesY.map((yVal, idx) => (
              <line
                key={idx}
                x1={paddingLeft}
                y1={yVal}
                x2={width - paddingRight}
                y2={yVal}
                stroke="#2c2e33"
                strokeWidth="1"
                strokeDasharray="4,4"
              />
            ))}

            {/* Gradient fill for spline rendering */}
            <defs>
              <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={activeColor} stopOpacity="0.14" />
                <stop offset="100%" stopColor={activeColor} stopOpacity="0.00" />
              </linearGradient>
            </defs>

            {chartStyle === "curve" ? (
              <>
                {/* Spline area backdrop */}
                <path d={areaPath} fill="url(#chartGradient)" className="transition-all duration-300" />

                {/* Spline stroke segment */}
                <path
                  d={linePath}
                  fill="none"
                  stroke={activeColor}
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="transition-all duration-300"
                />

                {/* Spline hover points */}
                {points.map((p, idx) => {
                  const isHovered = hoveredIndex === idx;
                  return (
                    <g key={idx}>
                      {/* Generous touch/hover box */}
                      <rect
                        x={p.x - 7}
                        y={paddingTop}
                        width="14"
                        height={chartHeight}
                        fill="transparent"
                        className="cursor-pointer"
                        onMouseEnter={() => setHoveredIndex(idx)}
                      />
                      <circle
                        cx={p.x}
                        cy={p.y}
                        r={isHovered ? "5" : "2.5"}
                        fill={activeColor}
                        stroke={isHovered ? "#ffffff" : "none"}
                        strokeWidth="1"
                        className="transition-all duration-200"
                        onMouseEnter={() => setHoveredIndex(idx)}
                      />
                    </g>
                  );
                })}
              </>
            ) : (
              <>
                {/* Column/Bar Graph implementation inside SVG */}
                {points.map((p, idx) => {
                  const isHovered = hoveredIndex === idx;
                  const barWidth = Math.max(5, (chartWidth / points.length) - 3.5);
                  const barX = p.x - barWidth / 2;
                  const barHeight = baselineY - p.y;

                  return (
                    <g key={idx}>
                      <rect
                        x={barX}
                        y={p.y}
                        width={barWidth}
                        height={Math.max(barHeight, 1.5)}
                        fill={activeColor}
                        rx="1.5"
                        ry="1.5"
                        className="transition-all duration-200 cursor-pointer"
                        style={{
                          opacity: hoveredIndex === null ? 0.78 : isHovered ? 1.0 : 0.28,
                        }}
                        onMouseEnter={() => setHoveredIndex(idx)}
                        onMouseLeave={() => setHoveredIndex(null)}
                      />
                    </g>
                  );
                })}
              </>
            )}

            {/* Axis labeling */}
            {points.length > 0 && (
              <>
                {/* Y-axis high/low ticks */}
                <text x={paddingLeft - 8} y={paddingTop + 3} textAnchor="end" fill="#909296" className="text-[8px] font-mono font-medium">
                  {metric === "cost" ? `$${maxValue.toFixed(2)}` : maxValue}
                </text>
                <text x={paddingLeft - 8} y={baselineY + 3} textAnchor="end" fill="#909296" className="text-[8px] font-mono font-medium">
                  {metric === "cost" ? `$${minValue.toFixed(2)}` : minValue}
                </text>

                {/* X-axis dates (first, middle, last) */}
                <text x={points[0].x} y={height - 2} textAnchor="start" fill="#909296" className="text-[8px] font-mono font-semibold">
                  {timeSeries[0].date.split("-").slice(1).join("/")}
                </text>
                <text x={points[Math.floor(points.length / 2)].x} y={height - 2} textAnchor="middle" fill="#909296" className="text-[8px] font-mono font-semibold">
                  {timeSeries[Math.floor(timeSeries.length / 2)].date.split("-").slice(1).join("/")}
                </text>
                <text x={points[points.length - 1].x} y={height - 2} textAnchor="end" fill="#909296" className="text-[8px] font-mono font-semibold">
                  {timeSeries[timeSeries.length - 1].date.split("-").slice(1).join("/")}
                </text>
              </>
            )}
          </svg>
        </div>

        {/* Dynamic Tooltip Overlay */}
        {hoveredIndex !== null && points[hoveredIndex] && (
          <div className="absolute top-2 left-10 bg-[#141517]/95 border border-[#2c2e33] p-2.5 rounded text-[10px] space-y-1 shadow-xl pointer-events-none fade-in font-sans">
            <div className="text-[#909296] font-mono flex items-center gap-1.5">
              <CalendarDays className="w-3 h-3 text-[#909296]" />
              <span>Date: {points[hoveredIndex].date}</span>
            </div>
            <div className="font-bold text-[#e9ecef]">
              {metric === "cost" ? (
                <span className="text-[#fab005]">Cost: ${points[hoveredIndex].cost.toFixed(4)}</span>
              ) : (
                <span className="text-[#20c997]">Calls: {points[hoveredIndex].calls} Executions</span>
              )}
            </div>
            <div className="text-[#909296] font-mono text-[9px] uppercase tracking-wide">
              Payload: {(points[hoveredIndex].tokens / 1000).toFixed(0)}K Tok / Failed: {points[hoveredIndex].failedCalls}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
