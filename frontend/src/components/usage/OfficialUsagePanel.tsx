import React from "react";
import { RefreshCw, ShieldCheck, AlertTriangle, Database } from "lucide-react";
import { OfficialUsageSummary, OfficialUsageProviderStatus } from "../../types";

interface Props {
  summary: OfficialUsageSummary | null;
  loading?: boolean;
  syncing?: boolean;
  onSync: () => void;
}

export default function OfficialUsagePanel({ summary, loading, syncing, onSync }: Props) {
  const statuses = summary?.status ?? {};
  const reconciliation = summary?.reconciliation ?? [];

  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5 space-y-5">
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-[#20c997]" />
            <h2 className="text-base font-semibold text-[#e9ecef]">Official Usage Snapshot</h2>
          </div>
          <p className="text-xs text-[#909296] mt-1">
            Shows dev/safety estimates beside official provider billing or account values. These numbers use different scopes and are not auto-compared.
          </p>
          <p className="text-[10px] text-[#fab005] mt-2">Official usage sync may query BigQuery.</p>
        </div>
        <button
          onClick={onSync}
          disabled={syncing}
          className="bg-[#25262b] hover:bg-[#2c2e33] disabled:opacity-60 border border-[#2c2e33] text-[#e9ecef] px-3 py-2 rounded text-xs font-bold flex items-center justify-center gap-2"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${syncing ? "animate-spin text-[#20c997]" : "text-[#909296]"}`} />
          {syncing ? "Syncing..." : "Sync now"}
        </button>
      </div>

      {loading ? (
        <div className="text-xs text-[#909296]">Loading official usage status...</div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <StatusCard provider="OpenAI official usage sync" status={statuses.openai} configuredLabel="Admin key" />
            <StatusCard provider="OpenRouter credits sync" status={statuses.openrouter} configuredLabel="Management key" />
            <StatusCard provider="Google BigQuery billing sync" status={statuses.google} configuredLabel="Credentials" />
          </div>

          <div className="overflow-x-auto border border-[#2c2e33] rounded">
            <table className="w-full text-xs">
              <thead className="bg-[#141517] text-[#909296] uppercase tracking-wider font-mono">
                <tr>
                  <th className="text-left px-3 py-2">Provider</th>
                  <th className="text-left px-3 py-2">Dev/Safety estimate</th>
                  <th className="text-left px-3 py-2">Official/account value</th>
                  <th className="text-left px-3 py-2">Status</th>
                  <th className="text-left px-3 py-2">Last synced</th>
                  <th className="text-left px-3 py-2">Notes</th>
                </tr>
              </thead>
              <tbody>
                {reconciliation.map((row) => (
                  <tr key={row.provider} className="border-t border-[#2c2e33] text-[#e9ecef]">
                    <td className="px-3 py-3 font-semibold">{labelProvider(row.provider)}</td>
                    <td className="px-3 py-3">
                      <div className="font-mono">{formatMoney(row.safety_estimated_cost_usd)}</div>
                      <div className="text-[10px] text-[#909296] mt-1">dev-only, excluded from real totals</div>
                    </td>
                    <td className="px-3 py-3">
                      <div className="font-mono">{row.provider_reported_cost_usd == null ? "Unavailable" : formatMoney(row.provider_reported_cost_usd)}</div>
                      <div className="text-[10px] text-[#909296] mt-1">{officialScopeLabel(row.provider, row.provider_reported_cost_usd)}</div>
                    </td>
                    <td className="px-3 py-3">
                      <span className={statusBadge(row.status)}>{labelStatus(row.status)}</span>
                    </td>
                    <td className="px-3 py-3 text-[#909296]">{formatDate(row.last_synced_at)}</td>
                    <td className="px-3 py-3 text-[#909296] max-w-sm">{row.notes.join(" ") || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

function StatusCard({ provider, status, configuredLabel }: { provider: string; status?: OfficialUsageProviderStatus; configuredLabel: string }) {
  const configured = Boolean(status?.admin_key_configured ?? status?.management_key_configured ?? status?.credentials_configured);
  const enabled = Boolean(status?.enabled);
  const ok = status?.status === "ok" || status?.status === "not_synced";

  return (
    <div className="bg-[#141517] border border-[#2c2e33] rounded p-4 min-h-40">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-sm font-bold text-[#e9ecef]">{provider}</h3>
        {ok ? <ShieldCheck className="w-4 h-4 text-[#20c997] shrink-0" /> : <AlertTriangle className="w-4 h-4 text-[#fab005] shrink-0" />}
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-[10px] font-mono">
        <span className={enabled ? "text-[#20c997]" : "text-[#909296]"}>{enabled ? "enabled" : "disabled"}</span>
        <span className={configured ? "text-[#20c997]" : "text-[#fab005]"}>{configuredLabel}: {configured ? "configured" : "missing"}</span>
        <span className="text-[#909296]">{status?.status ?? "unknown"}</span>
      </div>
      {status?.dataset && (
        <p className="text-[10px] text-[#909296] mt-3 font-mono">
          {status.project_id}/{status.dataset} tables: {status.tables_found ?? 0}
        </p>
      )}
      <p className="text-xs text-[#909296] mt-3">{messageFor(status)}</p>
      <p className="text-[10px] text-[#909296] mt-3">Last synced: {formatDate(status?.last_synced_at)}</p>
    </div>
  );
}

function messageFor(status?: OfficialUsageProviderStatus): string {
  if (!status) return "Waiting for status.";
  if (status.message) return status.message;
  if (status.status === "waiting_for_tables") return "Google billing export is enabled, but BigQuery tables are not available yet. Billing export can take time to appear.";
  if (status.status === "unavailable") return "Official provider data is unavailable. Check the required backend environment variable.";
  if (status.status === "disabled") return "Sync is disabled in backend configuration.";
  return "Ready for official usage sync.";
}

function statusBadge(status: string): string {
  const base = "rounded px-2 py-1 border font-mono text-[10px] ";
  if (status === "reconciled") return `${base}text-[#20c997] border-[#20c997]/20 bg-[#20c997]/10`;
  if (status === "provider_reported") return `${base}text-sky-300 border-sky-500/30 bg-sky-500/10`;
  if (status === "estimated") return `${base}text-[#fab005] border-[#fab005]/30 bg-[#fab005]/10`;
  if (status === "mock_only") return `${base}text-[#909296] border-[#2c2e33] bg-[#25262b]`;
  return `${base}text-rose-300 border-rose-500/30 bg-rose-500/10`;
}

function labelStatus(status: string): string {
  if (status === "provider_reported") return "provider value";
  if (status === "estimated") return "awaiting official";
  if (status === "mock_only") return "dev estimate only";
  return status.replace(/_/g, " ");
}

function labelProvider(provider: string): string {
  if (provider === "openai") return "OpenAI";
  if (provider === "openrouter") return "OpenRouter";
  if (provider === "google") return "Google/Gemini";
  return provider;
}

function formatDate(value?: string | null): string {
  if (!value) return "Never";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatMoney(value?: number | null): string {
  return `$${(value ?? 0).toFixed(6)}`;
}

function officialScopeLabel(provider: string, value?: number | null): string {
  if (value == null) return "not available from provider yet";
  if (provider === "openrouter") return "latest account balance snapshot";
  return "official provider billing/export";
}
