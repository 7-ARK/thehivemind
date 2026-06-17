import React, { useEffect, useState } from "react";
import {
  getUsageSummary,
  getUsageBudget,
  getUsageProviders,
  getUsageModels,
  getUsageAgents,
  getUsageTimeSeries,
  getUsageRecent,
  getExpensiveRuns,
  getUsageSearch,
  getUsageTokens,
  seedDemoUsage
} from "../../lib/api";

import {
  UsageSummary as SummaryType,
  BudgetStatus as BudgetType,
  ProviderUsage as ProviderType,
  ModelUsage as ModelType,
  AgentUsage as AgentType,
  UsageTimeSeriesPoint as TimePointType,
  RecentCall as CallType,
  ExpensiveRun as RunType,
  SearchUsageType,
  TokenBreakdownType
} from "../../types";

import UsageHeader from "./UsageHeader";
import BudgetHealthCard from "./BudgetHealthCard";
import UsageKpiGrid from "./UsageKpiGrid";
import UsageTimeSeries from "./UsageTimeSeries";
import ModelSpendBreakdown from "./ModelSpendBreakdown";
import ProviderSpendBreakdown from "./ProviderSpendBreakdown";
import AgentSpendBreakdown from "./AgentSpendBreakdown";
import TokenBreakdown from "./TokenBreakdown";
import LatencyReliabilityPanel from "./LatencyReliabilityPanel";
import SearchUsagePanel from "./SearchUsagePanel";
import RecentCallsTable from "./RecentCallsTable";
import ExpensiveRunsTable from "./ExpensiveRunsTable";
import UsageEmptyState from "./UsageEmptyState";
import UsageSkeleton from "./UsageSkeleton";

import { Info, ShieldAlert } from "lucide-react";

interface UsageDashboardProps {
  onRefreshTrigger?: number; // Let parent trigger dashboard refresh (e.g., after an orchestration run succeeds!)
}

export default function UsageDashboard({ onRefreshTrigger = 0 }: UsageDashboardProps) {
  const [range, setRange] = useState("30d");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // States
  const [summary, setSummary] = useState<SummaryType | null>(null);
  const [budget, setBudget] = useState<BudgetType | null>(null);
  const [providers, setProviders] = useState<ProviderType[]>([]);
  const [models, setModels] = useState<ModelType[]>([]);
  const [agents, setAgents] = useState<AgentType[]>([]);
  const [timeSeries, setTimeSeries] = useState<TimePointType[]>([]);
  const [recentCalls, setRecentCalls] = useState<CallType[]>([]);
  const [expensiveRuns, setExpensiveRuns] = useState<RunType[]>([]);
  const [searchData, setSearchData] = useState<SearchUsageType | null>(null);
  const [tokens, setTokens] = useState<TokenBreakdownType | null>(null);

  const fetchAllMetrics = async (showRefreshIndicator = false) => {
    if (showRefreshIndicator) setRefreshing(true);
    else setLoading(true);

    setError(null);
    try {
      const [
        summaryRes,
        budgetRes,
        providersRes,
        modelsRes,
        agentsRes,
        timeSeriesRes,
        recentRes,
        expensiveRes,
        searchRes,
        tokensRes,
      ] = await Promise.all([
        getUsageSummary(range),
        getUsageBudget(range),
        getUsageProviders(range),
        getUsageModels(range),
        getUsageAgents(range),
        getUsageTimeSeries(range),
        getUsageRecent(20),
        getExpensiveRuns(10),
        getUsageSearch(range),
        getUsageTokens(range),
      ]);

      setSummary(summaryRes);
      setBudget(budgetRes);
      setProviders(providersRes);
      setModels(modelsRes);
      setAgents(agentsRes);
      setTimeSeries(timeSeriesRes);
      setRecentCalls(recentRes);
      setExpensiveRuns(expensiveRes);
      setSearchData(searchRes);
      setTokens(tokensRes);
    } catch (e: any) {
      console.error(e);
      setError("Unable to compile model analytics. Connect to server first.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  // Pull elements on mount or range change
  useEffect(() => {
    fetchAllMetrics();
  }, [range, onRefreshTrigger]);

  const handleRefresh = () => {
    fetchAllMetrics(true);
  };

  const handleSeed = async () => {
    try {
      await seedDemoUsage();
      await fetchAllMetrics();
    } catch (e: any) {
      setError("Failed to dispatch seeding command to server database.");
    }
  };

  if (loading) {
    return (
      <div id="usage-dashboard-wrapper" className="space-y-6">
        <UsageHeader
          currentRange={range}
          setRange={setRange}
          onRefresh={handleRefresh}
          onSeedDemo={handleSeed}
          isRefreshing={refreshing}
        />
        <UsageSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div id="usage-dashboard-wrapper" className="space-y-6">
        <UsageHeader
          currentRange={range}
          setRange={setRange}
          onRefresh={handleRefresh}
          onSeedDemo={handleSeed}
          isRefreshing={refreshing}
        />
        <div className="bg-rose-950/20 border border-rose-900 text-rose-300 p-5 rounded-xl flex items-start gap-3.5 max-w-xl mx-auto my-12">
          <ShieldAlert className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
          <div>
            <h4 className="font-semibold text-gray-200 text-sm">Telemetry Connection Interrupted</h4>
            <p className="text-xs text-gray-400 mt-1 leading-relaxed">
              {error} Please verify that your Node development container or Python FastAPI server is active and accessible on the local environment port sequence.
            </p>
            <button
              onClick={handleRefresh}
              className="mt-4 px-3.5 py-1.5 bg-gray-950 hover:bg-gray-900 border border-gray-800 rounded-lg text-xs font-semibold text-gray-200 transition-colors cursor-pointer"
            >
              Retry Connection
            </button>
          </div>
        </div>
      </div>
    );
  }

  const isStateEmpty = !summary || summary.totalCalls === 0;

  return (
    <div id="usage-dashboard-wrapper" className="space-y-6 animate-fade-in text-sans select-none">
      {/* Header controls select */}
      <UsageHeader
        currentRange={range}
        setRange={setRange}
        onRefresh={handleRefresh}
        onSeedDemo={handleSeed}
        isRefreshing={refreshing}
      />

      {isStateEmpty ? (
        <UsageEmptyState
          onSeed={handleSeed}
          onRefresh={handleRefresh}
          isSeeding={refreshing}
        />
      ) : (
        <>
          {/* Main cost control guardrail */}
          {budget && <BudgetHealthCard budget={budget} />}

          <div className="bg-[#20c997]/10 border border-[#20c997]/20 text-[#20c997] rounded-lg px-4 py-3 text-xs">
            Usage rows can include mock or seeded telemetry. Mock runs show estimated live-equivalent cost for planning, while actual API cost remains $0.00.
          </div>

          {/* High level counters */}
          {summary && <UsageKpiGrid summary={summary} />}

          {/* Bento Grid Analytics */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Primary Column (Left 2 cols wide on desktop) */}
            <div className="lg:col-span-2 space-y-6">
              {/* Timeseries Graph */}
              {timeSeries.length > 0 && <UsageTimeSeries timeSeries={timeSeries} />}

              {/* Models Breakdown */}
              {models.length > 0 && <ModelSpendBreakdown models={models} />}

              {/* Providers Comparison matrix */}
              {providers.length > 0 && <ProviderSpendBreakdown providers={providers} />}
            </div>

            {/* Auxiliary metrics sidebar Column (Right 1 col wide) */}
            <div className="space-y-6">
              {/* Token payloads */}
              {tokens && <TokenBreakdown tokens={tokens} />}

              {/* Server Turnaround details */}
              {summary && (
                <LatencyReliabilityPanel
                  latencyData={{
                    averageLatency: summary.averageLatency,
                    p95Latency: summary.p95Latency,
                    slowestModel: "See model table",
                    slowestProvider: "See provider table",
                    successRate: summary.successRate,
                    totalFailedCalls: summary.failedCalls,
                  }}
                />
              )}

              {/* Web ground search logs */}
              {searchData && <SearchUsagePanel searchData={searchData} />}
            </div>
          </div>

          {/* Agent Role Cost Share table */}
          {agents.length > 0 && <AgentSpendBreakdown agents={agents} />}

          {/* Compound Expensive Run logs */}
          {expensiveRuns.length > 0 && <ExpensiveRunsTable runs={expensiveRuns} />}

          {/* API Log details table */}
          {recentCalls.length > 0 && <RecentCallsTable calls={recentCalls} />}
        </>
      )}
    </div>
  );
}
