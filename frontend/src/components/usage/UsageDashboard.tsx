import React, { useEffect, useState } from "react";
import {
  getOfficialUsageSummary,
  getRealAccountBilling,
  getRealProviderResponses,
  getRealUsageSummary,
  syncOfficialUsage,
} from "../../lib/api";
import { OfficialUsageSummary, RealOfficialBillingRecord, RealProviderUsageRecord, RealUsageSummary } from "../../types";
import UsageHeader from "./UsageHeader";
import OfficialUsagePanel from "./OfficialUsagePanel";
import UsageSkeleton from "./UsageSkeleton";
import { Database, ShieldAlert } from "lucide-react";

interface UsageDashboardProps {
  onRefreshTrigger?: number;
}

export default function UsageDashboard({ onRefreshTrigger = 0 }: UsageDashboardProps) {
  const [range, setRange] = useState("30d");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [syncingOfficial, setSyncingOfficial] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [officialUsage, setOfficialUsage] = useState<OfficialUsageSummary | null>(null);
  const [realSummary, setRealSummary] = useState<RealUsageSummary | null>(null);
  const [providerResponses, setProviderResponses] = useState<RealProviderUsageRecord[]>([]);
  const [accountBilling, setAccountBilling] = useState<{ records: RealOfficialBillingRecord[]; note: string } | null>(null);

  const fetchRealUsage = async (showRefreshIndicator = false) => {
    if (showRefreshIndicator) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const [officialRes, realSummaryRes, responsesRes, billingRes] = await Promise.all([
        getOfficialUsageSummary(range),
        getRealUsageSummary(),
        getRealProviderResponses(100),
        getRealAccountBilling(),
      ]);
      setOfficialUsage(officialRes);
      setRealSummary(realSummaryRes);
      setProviderResponses(responsesRes);
      setAccountBilling(billingRes);
    } catch (e: any) {
      setError("Unable to load real provider usage. Connect to the backend and check official usage sync configuration.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchRealUsage();
  }, [range, onRefreshTrigger]);

  const handleOfficialSync = async () => {
    setSyncingOfficial(true);
    setError(null);
    try {
      setOfficialUsage(await syncOfficialUsage(range));
      const [summaryRes, responsesRes, billingRes] = await Promise.all([getRealUsageSummary(), getRealProviderResponses(100), getRealAccountBilling()]);
      setRealSummary(summaryRes);
      setProviderResponses(responsesRes);
      setAccountBilling(billingRes);
    } catch (e: any) {
      setError("Official usage sync failed. Check backend logs and provider credentials.");
    } finally {
      setSyncingOfficial(false);
    }
  };

  if (loading) {
    return (
      <div id="usage-dashboard-wrapper" className="space-y-6">
        <UsageHeader currentRange={range} setRange={setRange} onRefresh={() => fetchRealUsage(true)} onSeedDemo={noopSeedDemo} isRefreshing={refreshing} />
        <UsageSkeleton />
      </div>
    );
  }

  return (
    <div id="usage-dashboard-wrapper" className="space-y-6 animate-fade-in text-sans select-none">
      <UsageHeader currentRange={range} setRange={setRange} onRefresh={() => fetchRealUsage(true)} onSeedDemo={noopSeedDemo} isRefreshing={refreshing} />

      {error && (
        <div className="bg-rose-950/20 border border-rose-900 text-rose-300 p-5 rounded-lg flex items-start gap-3.5">
          <ShieldAlert className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
          <div>
            <h4 className="font-semibold text-gray-200 text-sm">Real Usage Connection Interrupted</h4>
            <p className="text-xs text-gray-400 mt-1 leading-relaxed">{error}</p>
          </div>
        </div>
      )}

      <div className="bg-[#20c997]/10 border border-[#20c997]/20 text-[#20c997] rounded-lg px-4 py-3 text-xs">
        Real Usage &amp; Costs excludes mock/dev estimates by default. Totals below use provider-response, generation lookup, official billing, and account-balance records only.
      </div>

      <RealSummaryCards summary={realSummary} />

      <OfficialUsagePanel summary={officialUsage} syncing={syncingOfficial} onSync={handleOfficialSync} />

      <ProviderResponsesTable records={providerResponses} />

      <OfficialBillingTable payload={accountBilling} />
    </div>
  );
}

async function noopSeedDemo(): Promise<void> {
  return undefined;
}

function RealSummaryCards({ summary }: { summary: RealUsageSummary | null }) {
  const cards = [
    { label: "Actual Model Cost", value: `$${(summary?.model_provider_reported_cost_usd ?? summary?.run_level_provider_cost_usd ?? 0).toFixed(6)}`, desc: "provider-reported model/API spend" },
    { label: "Search Estimate", value: `$${(summary?.search_tool_estimated_cost_usd ?? 0).toFixed(6)}`, desc: "search_tool_estimate logs" },
    { label: "Run-Level Tokens", value: (summary?.run_level_tokens ?? 0).toLocaleString(), desc: "provider-given token counts" },
    { label: "Official Billing", value: `$${(summary?.official_billing_cost_usd ?? 0).toFixed(6)}`, desc: "official delayed billing/export" },
  ];
  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
      {cards.map((card) => (
        <div key={card.label} className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4">
          <div className="text-[10px] uppercase tracking-wider font-mono text-[#909296]">{card.label}</div>
          <div className="text-xl text-[#e9ecef] font-mono font-bold mt-2">{card.value}</div>
          <div className="text-xs text-[#909296] mt-1">{card.desc}</div>
        </div>
      ))}
    </div>
  );
}

function ProviderResponsesTable({ records }: { records: RealProviderUsageRecord[] }) {
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5 space-y-4">
      <SectionTitle title="Live Provider Usage by Run" />
      {records.length === 0 ? (
        <p className="text-xs text-[#909296]">No live provider-response or generation-lookup usage has been recorded yet.</p>
      ) : (
        <div className="overflow-x-auto border border-[#2c2e33] rounded">
          <table className="w-full text-xs">
            <thead className="bg-[#141517] text-[#909296] uppercase tracking-wider font-mono">
              <tr>
                {["Run", "Project", "Provider", "Model", "Actual Provider", "Agent", "Input", "Output", "Cached", "Reasoning", "Total", "Cost", "Source", "Timestamp"].map((heading) => (
                  <th key={heading} className="text-left px-3 py-2">{heading}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {records.map((record) => (
                <tr key={record.id} className="border-t border-[#2c2e33] text-[#e9ecef]">
                  <td className="px-3 py-3 font-mono">{shortId(record.run_id)}</td>
                  <td className="px-3 py-3">{record.project_id ?? "-"}</td>
                  <td className="px-3 py-3">{labelProvider(record.provider)}</td>
                  <td className="px-3 py-3">{record.requested_model ?? record.actual_model ?? "-"}</td>
                  <td className="px-3 py-3">{record.provider_name ?? record.actual_model ?? "-"}</td>
                  <td className="px-3 py-3">{record.agent_name ?? "-"}</td>
                  <td className="px-3 py-3 font-mono">{record.input_tokens}</td>
                  <td className="px-3 py-3 font-mono">{record.output_tokens}</td>
                  <td className="px-3 py-3 font-mono">{record.cached_tokens}</td>
                  <td className="px-3 py-3 font-mono">{record.reasoning_tokens}</td>
                  <td className="px-3 py-3 font-mono">{record.total_tokens}</td>
                  <td className="px-3 py-3 font-mono">{record.provider_reported_cost_usd == null ? "pending" : `$${record.provider_reported_cost_usd.toFixed(6)}`}</td>
                  <td className="px-3 py-3">{record.source}</td>
                  <td className="px-3 py-3 text-[#909296]">{formatDate(record.timestamp)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function OfficialBillingTable({ payload }: { payload: { records: RealOfficialBillingRecord[]; note: string } | null }) {
  const records = aggregateOfficialBillingCards(payload?.records ?? []);
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5 space-y-4">
      <SectionTitle title="Official Provider Billing" />
      <p className="text-xs text-[#909296]">{payload?.note ?? "Official billing/account data appears here after sync."}</p>
      {records.length === 0 ? (
        <p className="text-xs text-[#909296]">No official billing or account-balance records are available yet.</p>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          {records.map((record) => (
            <div key={record.id} className="bg-[#141517] border border-[#2c2e33] rounded p-4">
              <div className="flex items-center gap-2">
                <Database className="w-4 h-4 text-[#20c997]" />
                <div className="text-sm font-bold text-[#e9ecef]">{labelProvider(record.provider)}</div>
              </div>
              <div className="mt-2 text-xl font-mono text-[#e9ecef]">{record.provider_reported_cost_usd == null ? "Unavailable" : `$${record.provider_reported_cost_usd.toFixed(6)}`}</div>
              <div className="mt-2 flex flex-wrap gap-2 text-[10px] font-mono text-[#909296]">
                <span>{record.source}</span>
                <span>{record.scope}</span>
                <span>{record.currency}</span>
              </div>
              <p className="text-xs text-[#909296] mt-3">{record.note}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function aggregateOfficialBillingCards(records: RealOfficialBillingRecord[]): RealOfficialBillingRecord[] {
  const openrouterLatest = latestRecord(records.filter((record) => record.provider === "openrouter" && record.source === "provider_account_balance"));
  const openai = aggregateProviderBilling("openai", records);
  const google = aggregateProviderBilling("google", records);
  const exa = aggregateProviderBilling("exa", records);
  return [openrouterLatest, openai, google, exa].filter(Boolean) as RealOfficialBillingRecord[];
}

function aggregateProviderBilling(provider: "openai" | "google" | "exa", records: RealOfficialBillingRecord[]): RealOfficialBillingRecord | null {
  const providerRecords = records.filter((record) => record.provider === provider && record.source === "provider_official_billing");
  if (providerRecords.length === 0) return null;
  if (providerRecords.length === 1) return providerRecords[0];

  const latest = latestRecord(providerRecords) ?? providerRecords[0];
  const costValues = providerRecords
    .map((record) => record.provider_reported_cost_usd)
    .filter((value): value is number => typeof value === "number");
  const cost = costValues.length > 0 ? Number(costValues.reduce((total, value) => total + value, 0).toFixed(6)) : null;

  return {
    ...latest,
    id: `${provider}-official-billing-aggregate`,
    provider_reported_cost_usd: cost,
    sku: null,
    note: provider === "openai"
      ? `Aggregated official OpenAI billing from ${providerRecords.length} synced row(s).`
      : `Aggregated Google/Gemini billing export from ${providerRecords.length} synced row(s).`,
  };
}

function latestRecord(records: RealOfficialBillingRecord[]): RealOfficialBillingRecord | null {
  if (records.length === 0) return null;
  return records.reduce((latest, record) => (timestampMs(record.created_at) > timestampMs(latest.created_at) ? record : latest), records[0]);
}

function timestampMs(value?: string | null): number {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function SectionTitle({ title }: { title: string }) {
  return <h2 className="text-base font-semibold text-[#e9ecef]">{title}</h2>;
}

function shortId(value?: string | null): string {
  return value ? value.slice(0, 8) : "-";
}

function labelProvider(provider: string): string {
  if (provider === "openai") return "OpenAI";
  if (provider === "openrouter") return "OpenRouter";
  if (provider === "google" || provider === "gemini") return "Google/Gemini";
  return provider;
}

function formatDate(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
