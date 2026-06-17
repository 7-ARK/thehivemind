import { X, Database, RefreshCw } from "lucide-react";
import React, { useEffect, useMemo, useState } from "react";
import {
  getProjectChanges,
  getRun,
  getRunArtifacts,
  getRunCommands,
  getRunEvents,
} from "../../lib/api";
import { collectRunCommands, collectRunFiles, mergeArtifacts } from "../../lib/runSummary";
import { ArtifactRecord, CommandResult, ProjectChange, RunEvent, RunResult } from "../../types";
import RunArtifactsPanel from "./RunArtifactsPanel";
import RunCommandsPanel from "./RunCommandsPanel";
import RunFileChangesPanel from "./RunFileChangesPanel";
import RunFinalReportPanel from "./RunFinalReportPanel";
import RunTimelinePanel from "./RunTimelinePanel";
import RunUsagePanel from "./RunUsagePanel";

interface Props {
  runId: string;
  projectId?: string;
  onClose?: () => void;
  onOpenProject?: (projectId: string) => void;
}

export default function RunDetailViewer({ runId, projectId, onClose, onOpenProject }: Props) {
  const [run, setRun] = useState<RunResult | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactRecord[]>([]);
  const [commands, setCommands] = useState<CommandResult[]>([]);
  const [changes, setChanges] = useState<ProjectChange[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const resolvedProjectId = run?.project_id ?? projectId;

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const runPayload = await getRun(runId);
      setRun(runPayload);
      const [eventsResult, artifactsResult, commandsResult, changesResult] = await Promise.allSettled([
        getRunEvents(runId),
        getRunArtifacts(runId),
        getRunCommands(runId),
        runPayload.project_id ? getProjectChanges(runPayload.project_id) : Promise.resolve({ project_id: "", changes: [] }),
      ]);
      setEvents(eventsResult.status === "fulfilled" ? eventsResult.value : runPayload.events ?? []);
      setArtifacts(artifactsResult.status === "fulfilled" ? mergeArtifacts(runPayload.artifacts ?? [], artifactsResult.value) : runPayload.artifacts ?? []);
      setCommands(commandsResult.status === "fulfilled" ? commandsResult.value : runPayload.commands_run ?? []);
      const allChanges = changesResult.status === "fulfilled" ? changesResult.value.changes : [];
      setChanges(allChanges.filter((change) => change.run_id === runId));
    } catch (err: any) {
      setError(err.message || "Run not found or backend unavailable.");
      setRun(null);
      setEvents([]);
      setArtifacts([]);
      setCommands([]);
      setChanges([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [runId]);

  const modelsUsed = useMemo(() => {
    const values = new Set<string>();
    events.forEach((event) => values.add(event.model_used));
    run?.usage_summary?.models_used?.forEach((model) => values.add(model));
    return Array.from(values);
  }, [events, run]);

  const fileSummary = run ? collectRunFiles(run, changes) : { created: [], updated: [] };
  const displayCommands = run ? collectRunCommands(run, commands) : [];
  const displayArtifacts = run ? mergeArtifacts(run.artifacts ?? [], artifacts) : artifacts;

  return (
    <div className="fixed inset-0 z-50 bg-[#08090b]/80 backdrop-blur-sm flex items-start justify-center p-3 sm:p-6 overflow-y-auto">
      <div className="w-full max-w-7xl bg-[#141517] border border-[#2c2e33] rounded-lg shadow-2xl">
        <header className="sticky top-0 z-10 bg-[#1a1b1e]/95 backdrop-blur border-b border-[#2c2e33] p-4 rounded-t-lg">
          <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
            <div>
              <div className="text-[10px] text-[#20c997] uppercase tracking-wider font-mono font-bold">Run Detail Viewer</div>
              <h2 className="text-lg font-bold text-[#e9ecef] mt-1 font-mono break-all">{runId}</h2>
              <div className="flex flex-wrap gap-2 mt-3 text-[10px] font-mono">
                <Badge tone={run?.mode === "live" ? "amber" : "green"}>{run?.mode ?? "loading"}</Badge>
                <Badge tone="neutral">{run?.status ?? "loading"}</Badge>
                <Badge tone="neutral">{run?.run_type ?? "run_type"}</Badge>
                {resolvedProjectId && <Badge tone="green">{resolvedProjectId}</Badge>}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {resolvedProjectId && onOpenProject && (
                <button onClick={() => onOpenProject(resolvedProjectId)} className="bg-[#25262b] border border-[#2c2e33] hover:bg-[#2c2e33] text-[#20c997] px-3 py-2 rounded text-xs font-bold flex items-center gap-2">
                  <Database className="w-4 h-4" />
                  Project Workspace
                </button>
              )}
              <button onClick={load} className="bg-[#25262b] border border-[#2c2e33] hover:bg-[#2c2e33] text-[#e9ecef] px-3 py-2 rounded text-xs font-bold flex items-center gap-2">
                <RefreshCw className="w-4 h-4" />
                Refresh
              </button>
              {onClose && (
                <button onClick={onClose} className="bg-[#25262b] border border-[#2c2e33] hover:bg-[#2c2e33] text-[#e9ecef] px-3 py-2 rounded text-xs font-bold flex items-center gap-2">
                  <X className="w-4 h-4" />
                  Close
                </button>
              )}
            </div>
          </div>
        </header>

        <main className="p-4 sm:p-5 space-y-5">
          {loading && <div className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4 text-xs text-[#909296]">Loading run details...</div>}
          {error && <div className="bg-rose-500/10 border border-rose-500/30 text-rose-300 rounded-lg p-4 text-xs">{error}</div>}
          {run && (
            <>
              <SummaryGrid run={run} artifactsCount={displayArtifacts.length} changesCount={fileSummary.created.length + fileSummary.updated.length} commandsCount={displayCommands.length} modelsCount={modelsUsed.length} />
              <div className="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-5">
                <div className="space-y-5">
                  <RunTimelinePanel events={events.length ? events : run.events ?? []} mode={run.mode} />
                  <RunFinalReportPanel run={run} />
                </div>
                <aside className="space-y-5">
                  <RunUsagePanel run={run} events={events.length ? events : run.events ?? []} />
                  <RunCommandsPanel commands={displayCommands} />
                  <RunFileChangesPanel changes={changes} created={fileSummary.created} updated={fileSummary.updated} />
                  <RunArtifactsPanel artifacts={displayArtifacts} />
                </aside>
              </div>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function SummaryGrid({ run, artifactsCount, changesCount, commandsCount, modelsCount }: { run: RunResult; artifactsCount: number; changesCount: number; commandsCount: number; modelsCount: number }) {
  const costLabel = run.mode === "mock" ? "Estimated If Live" : "Cost";
  return (
    <section className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-8 gap-3">
      <Metric label={costLabel} value={`$${run.metrics.total_estimated_cost_usd.toFixed(6)}`} />
      {run.mode === "mock" && <Metric label="Actual API Cost" value="$0.00" />}
      <Metric label="Tokens" value={run.metrics.total_estimated_tokens.toLocaleString()} />
      <Metric label="Agents" value={String(run.metrics.agents_used)} />
      <Metric label="Models" value={String(modelsCount)} />
      <Metric label="Artifacts" value={String(artifactsCount)} />
      <Metric label="File Changes" value={String(changesCount)} />
      <Metric label="Commands" value={String(commandsCount)} />
      <Metric label="Runtime" value={`${run.metrics.run_duration_seconds}s`} />
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-[#1a1b1e] border border-[#2c2e33] rounded p-3">
      <div className="text-[10px] text-[#909296] uppercase font-mono">{label}</div>
      <div className="text-xs text-[#e9ecef] font-mono mt-1 truncate">{value}</div>
    </div>
  );
}

function Badge({ children, tone }: { children: React.ReactNode; tone: "green" | "amber" | "neutral" }) {
  const color = tone === "green" ? "text-[#20c997] border-[#20c997]/20 bg-[#20c997]/10" : tone === "amber" ? "text-[#fab005] border-[#fab005]/30 bg-[#fab005]/10" : "text-[#909296] border-[#2c2e33] bg-[#25262b]";
  return <span className={`px-2 py-1 rounded border ${color}`}>{children}</span>;
}
