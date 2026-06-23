import { X, Database, RefreshCw } from "lucide-react";
import React, { useEffect, useMemo, useState } from "react";
import {
  getProjectChanges,
  getRun,
  getRunArtifacts,
  getRunAgentPlan,
  getRunCommands,
  getRunEvents,
  getRunModelSelection,
  getRecentSearchLogs,
} from "../../lib/api";
import { collectRunCommands, collectRunFiles, mergeArtifacts } from "../../lib/runSummary";
import { ArtifactRecord, CommandResult, ProjectChange, RunEvent, RunResult, SearchLogRecord } from "../../types";
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
  const [agentPlan, setAgentPlan] = useState<Record<string, any>>({});
  const [modelSelection, setModelSelection] = useState<Record<string, any>>({});
  const [searchLogs, setSearchLogs] = useState<SearchLogRecord[]>([]);
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
      const [agentPlanResult, modelSelectionResult] = await Promise.allSettled([
        getRunAgentPlan(runId),
        getRunModelSelection(runId),
      ]);
      const searchLogsResult = await getRecentSearchLogs(100);
      setEvents(eventsResult.status === "fulfilled" ? eventsResult.value : runPayload.events ?? []);
      setArtifacts(artifactsResult.status === "fulfilled" ? mergeArtifacts(runPayload.artifacts ?? [], artifactsResult.value) : runPayload.artifacts ?? []);
      setCommands(commandsResult.status === "fulfilled" ? commandsResult.value : runPayload.commands_run ?? []);
      const allChanges = changesResult.status === "fulfilled" ? changesResult.value.changes : [];
      setChanges(allChanges.filter((change) => change.run_id === runId));
      setAgentPlan(agentPlanResult.status === "fulfilled" ? agentPlanResult.value.agent_plan as Record<string, any> : runPayload.agent_plan ?? {});
      setModelSelection(modelSelectionResult.status === "fulfilled" ? modelSelectionResult.value.model_selection : runPayload.model_selection ?? {});
      setSearchLogs(searchLogsResult.filter((log) => log.run_id === runId));
    } catch (err: any) {
      setError(err.message || "Run not found or backend unavailable.");
      setRun(null);
      setEvents([]);
      setArtifacts([]);
      setCommands([]);
      setChanges([]);
      setAgentPlan({});
      setModelSelection({});
      setSearchLogs([]);
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
                  <RunSearchPanel logs={searchLogs} artifacts={displayArtifacts} />
                  <RunMemoryPanel run={run} />
                  <RunBusinessBuilderPanel run={run} />
                  <RunRealCodingPanel run={run} />
                  <RunPlanPanel agentPlan={agentPlan} modelSelection={modelSelection} />
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

function RunBusinessBuilderPanel({ run }: { run: RunResult }) {
  const detail = run.usage_summary?.business_builder;
  if (!detail) return null;
  const approvals = Array.isArray(detail.approvals_needed) ? detail.approvals_needed.map(String) : [];
  const blocked = Array.isArray(detail.blocked_external_actions) ? detail.blocked_external_actions.map(String) : [];
  const deferred = Array.isArray(detail.deferred_to_phase_2) ? detail.deferred_to_phase_2.map(String) : [];
  const search = detail.search_status ?? {};
  const memory = detail.memory_status ?? {};
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono">Business Builder Phase 1</h3>
          <p className="text-xs text-[#909296] mt-1">Planning package only. No website, app, deployment, asset, or external action was created.</p>
        </div>
        <span className="text-[10px] text-[#20c997] border border-[#20c997]/20 bg-[#20c997]/10 rounded px-2 py-1 font-mono">phase 1</span>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Metric label="Phase" value={String(detail.phase ?? 1)} />
        <Metric label="Status" value={String(detail.status ?? "planning_complete")} />
        <Metric label="Build Status" value={String(detail.build_status ?? "Not built")} />
        <Metric label="Build Started" value={String(Boolean(detail.build_started))} />
        <Metric label="Build Allowed" value={String(Boolean(detail.build_allowed))} />
        <Metric label="Execution Mode" value={String(detail.execution_mode ?? "unknown")} />
        <Metric label="Actual Provider" value={String(detail.actual_provider ?? "unknown")} />
        <Metric label="Actual Model" value={String(detail.actual_model ?? "none")} />
        <Metric label="Live Target" value={String(detail.live_strategic_planner_target ?? "gpt-5.5:flex")} />
        <Metric label="Live Call" value={String(Boolean(detail.live_call_made))} />
        <Metric label="Call Status" value={String(detail.provider_call_status ?? "unknown")} />
        <Metric label="Search Used" value={String(Boolean(search.used))} />
        <Metric label="Search Sources" value={String(search.source_count ?? 0)} />
        <Metric label="Memory Retrieved" value={String(memory.retrieved_count ?? 0)} />
      </div>
      <MiniList title="Approvals Needed" items={approvals} empty="No approvals listed." />
      <MiniList title="Blocked External Actions" items={blocked} empty="No blocked external actions listed." />
      <MiniList title="Deferred To Phase 2" items={deferred} empty="Nothing deferred." />
    </section>
  );
}

function RunRealCodingPanel({ run }: { run: RunResult }) {
  const detail = run.usage_summary?.real_coding_agent;
  if (!detail || Object.keys(detail).length === 0) return null;
  const filesInspected = Array.isArray(detail.files_inspected) ? detail.files_inspected : [];
  const filesSelected = Array.isArray(detail.files_selected) ? detail.files_selected : [];
  const filesChanged = Array.isArray(detail.files_changed) ? detail.files_changed : [];
  const rejectedFiles = Array.isArray(detail.rejected_files) ? detail.rejected_files : [];
  const validation = detail.validation ?? {};
  const scope = detail.allowed_user_file_scope ?? {};
  const patchCommands = Array.isArray(detail.validation_commands) ? detail.validation_commands : [];
  const sanity = run.usage_summary?.project_sanity_validation ?? {};
  const sanityCommands = Array.isArray(sanity.commands) ? sanity.commands : run.commands_run ?? [];
  const memoryUsed = Array.isArray(detail.memory_used) ? detail.memory_used : [];
  const memoryExclusions = Array.isArray(detail.memory_exclusions) ? detail.memory_exclusions : [];
  const repair = detail.repair_loop ?? {};
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono">Real Coding Agent</h3>
          <p className="text-xs text-[#909296] mt-1">
            {detail.hardcoded_fallback_used
              ? "Template fallback used. No real coding model call was made."
              : "Reusable coding path inspected files, generated structured patch output, and applied or validated it."}
          </p>
        </div>
        <span className={detail.hardcoded_fallback_used ? "text-[10px] text-[#fab005] border border-[#fab005]/30 bg-[#fab005]/10 rounded px-2 py-1 font-mono" : "text-[10px] text-[#20c997] border border-[#20c997]/20 bg-[#20c997]/10 rounded px-2 py-1 font-mono"}>
          {detail.hardcoded_fallback_used ? "fallback" : "real coding"}
        </span>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Metric label="Enabled" value={String(Boolean(detail.enabled))} />
        <Metric label="Provider" value={String(detail.actual_provider ?? "unknown")} />
        <Metric label="Model" value={String(detail.selected_model ?? "unknown")} />
        <Metric label="Fallback" value={String(detail.fallback_model ?? "none")} />
        <Metric label="Fallback Used" value={String(Boolean(detail.fallback_model_used))} />
        <Metric label="Live Call" value={String(Boolean(detail.live_call_made))} />
        <Metric label="Mock Simulated" value={String(Boolean(detail.mock_simulated))} />
        <Metric label="Dry Run" value={String(Boolean(detail.dry_run))} />
        <Metric label="Patch Applied" value={String(Boolean(detail.patch_applied))} />
        <Metric label="Parser" value={String(detail.parser_route ?? "n/a")} />
        <Metric label="Max Output" value={String(detail.requested_max_output_tokens ?? "n/a")} />
        <Metric label="Response Format" value={String(detail.response_format_requested ?? "n/a")} />
        <Metric label="Finish Reason" value={String(detail.provider_response_finish_reason ?? "n/a")} />
        <Metric label="Output Tokens" value={String(detail.actual_output_tokens ?? "n/a")} />
        <Metric label="Content Source" value={String(detail.content_source ?? "n/a")} />
        <Metric label="Scope" value={String(scope.scope_type ?? "unknown")} />
        <Metric label="Inspected" value={String(filesInspected.length)} />
        <Metric label="Selected" value={String(filesSelected.length)} />
        <Metric label="Changed" value={String(filesChanged.length)} />
        <Metric label="Repair Attempts" value={String(detail.repair_attempts ?? 0)} />
      </div>
      <MiniList title="Files Selected" items={filesSelected} empty="No files selected." />
      {Array.isArray(scope.allowed_user_files) && scope.allowed_user_files.length > 0 && (
        <MiniList title="Allowed User File Scope" items={scope.allowed_user_files} empty="No explicit scope." />
      )}
      <MiniList title="Files Changed" items={filesChanged} empty="No files changed." />
      {rejectedFiles.length > 0 && <MiniList title="Rejected Files" items={rejectedFiles} empty="No rejected files." />}
      <div className="bg-[#141517] border border-[#2c2e33] rounded p-3">
        <h4 className="text-[10px] text-[#909296] uppercase font-mono font-bold">Repair Loop</h4>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 mt-3">
          <Metric label="Repair Enabled" value={String(Boolean(repair.repair_enabled))} />
          <Metric label="Attempts" value={`${String(repair.attempts_made ?? detail.repair_attempts ?? 0)} / ${String(repair.max_attempts ?? 0)}`} />
          <Metric label="Initial Validation" value={repair.initial_validation_failed ? "failed" : "not_failed"} />
          <Metric label="Repair Validation" value={repair.repair_validation_passed === true ? "passed" : repair.repair_validation_passed === false ? "failed" : "n/a"} />
          <Metric label="Rollback" value={repair.rollback_attempted ? (repair.rollback_succeeded ? "succeeded" : "failed") : "not_attempted"} />
          <Metric label="Final Result" value={String(repair.final_result ?? "not_attempted")} />
        </div>
        {repair.not_attempted_reason && <p className="text-xs text-[#909296] mt-2">{String(repair.not_attempted_reason)}</p>}
      </div>
      {detail.no_change_reason && (
        <div className="bg-[#141517] border border-[#2c2e33] rounded p-3">
          <h4 className="text-[10px] text-[#909296] uppercase font-mono font-bold">No Change Reason</h4>
          <p className="text-xs text-[#909296] mt-2">{String(detail.no_change_reason)}</p>
        </div>
      )}
      {detail.parse_error && (
        <div className="bg-[#141517] border border-[#ff6b6b]/40 rounded p-3">
          <h4 className="text-[10px] text-[#ff8787] uppercase font-mono font-bold">Provider Output Rejected</h4>
          <p className="text-xs text-[#fab005] mt-2">{String(detail.parse_error)}</p>
        </div>
      )}
      <div className="bg-[#141517] border border-[#2c2e33] rounded p-3">
        <h4 className="text-[10px] text-[#909296] uppercase font-mono font-bold">Patch Validation</h4>
        <p className="text-xs text-[#909296] mt-2">Patch accepted: <span className="text-[#e9ecef] font-mono">{String(Boolean(validation.accepted))}</span></p>
        <p className="text-xs text-[#909296] mt-2">Scope validation: <span className="text-[#e9ecef] font-mono">{Array.isArray(validation.violations) && validation.violations.some((item: string) => item.toLowerCase().includes("scope")) ? "failed" : "passed"}</span></p>
        <p className="text-xs text-[#909296] mt-2">Protected path validation: <span className="text-[#e9ecef] font-mono">{Array.isArray(validation.violations) && validation.violations.some((item: string) => item.toLowerCase().includes("protected")) ? "failed" : "passed"}</span></p>
        {Array.isArray(validation.violations) && validation.violations.length > 0 && <p className="text-xs text-[#fab005] mt-2">{validation.violations.join("; ")}</p>}
        <p className="text-xs text-[#909296] mt-2">Patch-specific validation commands: <span className="text-[#e9ecef] font-mono">{patchCommands.length}</span></p>
      </div>
      <div className="bg-[#141517] border border-[#2c2e33] rounded p-3">
        <h4 className="text-[10px] text-[#909296] uppercase font-mono font-bold">Project Sanity Validation</h4>
        <p className="text-xs text-[#909296] mt-2">Safe commands executed: <span className="text-[#e9ecef] font-mono">{sanityCommands.length}</span></p>
        <p className="text-xs text-[#909296] mt-2">Result: <span className="text-[#e9ecef] font-mono">{String(sanity.result ?? (sanityCommands.length ? "reviewed" : "not_run"))}</span></p>
        <p className="text-xs text-[#909296] mt-2">{String(sanity.reason ?? "Project sanity commands are separate from patch validation.")}</p>
        {sanityCommands.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {sanityCommands.slice(0, 4).map((item: any, index: number) => (
              <span key={`${index}-${Array.isArray(item.command) ? item.command.join(" ") : "command"}`} className="text-[10px] text-[#e9ecef] bg-[#25262b] border border-[#2c2e33] rounded px-2 py-1 font-mono break-all">
                {Array.isArray(item.command) ? item.command.join(" ") : String(item.command ?? "command")}
              </span>
            ))}
          </div>
        )}
      </div>
      {memoryUsed.length > 0 && (
        <MiniList title="Memory Used" items={memoryUsed.map((item: any) => String(item.title ?? item.summary ?? "memory item"))} empty="No memory used." />
      )}
      {memoryExclusions.length > 0 && <MiniList title="Excluded Low-Quality Memory" items={memoryExclusions.map(String)} empty="No memory excluded." />}
    </section>
  );
}

function MiniList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div className="bg-[#141517] border border-[#2c2e33] rounded p-3">
      <h4 className="text-[10px] text-[#909296] uppercase font-mono font-bold">{title}</h4>
      {items.length === 0 ? (
        <p className="text-xs text-[#909296] mt-2">{empty}</p>
      ) : (
        <div className="mt-2 flex flex-wrap gap-2">
          {items.slice(0, 12).map((item) => (
            <span key={item} className="text-[10px] text-[#e9ecef] bg-[#25262b] border border-[#2c2e33] rounded px-2 py-1 font-mono break-all">
              {item}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function RunSearchPanel({ logs, artifacts }: { logs: SearchLogRecord[]; artifacts: ArtifactRecord[] }) {
  if (logs.length === 0) return null;
  const log = logs[0];
  const sourcesArtifact = artifacts.find((artifact) => artifact.name === "research_sources.json");
  const estimate = log.cost?.estimated_usd ?? 0;
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono">Search</h3>
          <p className="text-xs text-[#909296] mt-1">{searchStatusSentence(log)}</p>
        </div>
        <span className="text-[10px] text-[#20c997] border border-[#20c997]/20 bg-[#20c997]/10 rounded px-2 py-1 font-mono">
          {formatSearchStatus(log.status)}
        </span>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Metric label="Provider" value={labelSearchProvider(log.provider_id)} />
        <Metric label="Mode" value={String(log.mode ?? "unknown")} />
        <Metric label="Sources" value={String(log.source_count ?? 0)} />
        <Metric label="Search Estimate" value={`$${estimate.toFixed(6)}`} />
        <Metric label="Mock Fixture" value={String(Boolean(log.mock_fixture))} />
        <Metric label="Cache Hit" value={String(Boolean(log.cache_hit))} />
        {log.request_id && <Metric label="Request ID" value={log.request_id} />}
        {sourcesArtifact && <Metric label="Artifact" value={sourcesArtifact.name} />}
      </div>
      {log.error_message && <p className="text-xs text-[#fab005]">{log.error_message}</p>}
    </section>
  );
}

function RunMemoryPanel({ run }: { run: RunResult }) {
  const snippets = run.memory?.retrieved_snippets ?? [];
  const updates = run.memory_updates ?? [];
  const control = run.usage_summary?.memory_control ?? {};
  const useMemory = control.use_memory !== false;
  const retrievedCount = typeof control.retrieved_count === "number" ? control.retrieved_count : snippets.length;
  const ingestedCount = typeof control.ingested_after_run_count === "number" ? control.ingested_after_run_count : updates.length;
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4 space-y-3">
      <div>
        <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono">Memory</h3>
        <p className="text-xs text-[#909296] mt-1">
          Memory: <span className={useMemory ? "text-[#20c997] font-mono" : "text-[#fab005] font-mono"}>{useMemory ? "enabled" : "disabled"}</span>
        </p>
        <p className="text-xs text-[#909296] mt-1">
          Retrieved: <span className="text-[#e9ecef] font-mono">{retrievedCount}</span>. Ingested after run: <span className="text-[#e9ecef] font-mono">{ingestedCount}</span>.
        </p>
        {!useMemory && <p className="text-xs text-[#909296] mt-2">Historical memory retrieval was disabled for this run. Post-run ingestion is separate and only stores this run for future use.</p>}
      </div>
      {!useMemory || snippets.length === 0 ? (
        <p className="text-xs text-[#909296]">No memory snippets were injected for this run, or memory was disabled.</p>
      ) : (
        <div className="space-y-2">
          {snippets.slice(0, 5).map((snippet, index) => (
            <div key={`${snippet.title}-${index}`} className="bg-[#141517] border border-[#2c2e33] rounded p-3">
              <div className="text-xs text-[#e9ecef] font-bold">{snippet.title}</div>
              <p className="text-xs text-[#909296] mt-1">{snippet.content}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function RunPlanPanel({ agentPlan, modelSelection }: { agentPlan: Record<string, any>; modelSelection: Record<string, any> }) {
  const selectedAgents = Array.isArray(agentPlan?.selected_agents) ? agentPlan.selected_agents : [];
  const skippedAgents = Array.isArray(agentPlan?.skipped_agents) ? agentPlan.skipped_agents : [];
  if (selectedAgents.length === 0 && Object.keys(modelSelection ?? {}).length === 0) return null;
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono">Agent Plan & Model Selection</h3>
          <p className="text-xs text-[#909296] mt-1">Workflow: <span className="text-[#20c997] font-mono">{String(agentPlan?.selected_workflow ?? "unknown")}</span></p>
          {agentPlan?.search_needed && (
            <p className="text-xs text-[#909296] mt-1">
              Search:{" "}
              <span className={agentPlan?.search_unavailable ? "text-[#fab005] font-mono" : "text-[#20c997] font-mono"}>
                {agentPlan?.search_unavailable ? "unavailable" : String(agentPlan?.selected_search_provider?.id ?? "selected")}
              </span>
            </p>
          )}
        </div>
        {Array.isArray(agentPlan?.blocked_actions) && agentPlan.blocked_actions.length > 0 && (
          <span className="text-[10px] text-[#fab005] border border-[#fab005]/30 bg-[#fab005]/10 rounded px-2 py-1 font-mono">
            constraints applied: {agentPlan.blocked_actions.join(", ")}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {selectedAgents.map((agent: any) => {
          const selected = agent.selected_model ?? modelSelection?.[agent.agent_id] ?? {};
          return (
            <div key={agent.agent_id} className="bg-[#141517] border border-[#2c2e33] rounded p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-sm text-[#e9ecef] font-bold">{labelAgent(agent.agent_id)}</div>
                  <p className="text-xs text-[#909296] mt-1">{agent.objective}</p>
                </div>
                <span className="text-[10px] text-[#20c997] font-mono bg-[#20c997]/10 border border-[#20c997]/20 px-2 py-1 rounded">
                  {selected.selected_model_id ?? "manual"}
                </span>
              </div>
              {selected.reason && <p className="text-xs text-[#ced4da] mt-3">{selected.reason}</p>}
              <div className="flex flex-wrap gap-2 mt-3 text-[10px] text-[#909296] font-mono">
                {selected.fallback_model_id && <span>fallback: {selected.fallback_model_id}</span>}
                {typeof selected.confidence === "number" && <span>confidence: {Math.round(selected.confidence * 100)}%</span>}
                {agent.allowed_tools?.length > 0 && <span>tools: {agent.allowed_tools.join(", ")}</span>}
                {agent.selected_search_provider?.id && <span>search: {agent.selected_search_provider.id}</span>}
              </div>
            </div>
          );
        })}
      </div>

      {skippedAgents.length > 0 && (
        <div>
          <div className="text-[10px] text-[#909296] uppercase tracking-wider font-mono mb-2">Skipped Agents</div>
          <div className="flex flex-wrap gap-2">
            {skippedAgents.slice(0, 8).map((agent: any) => (
              <span key={agent.agent_id} className="text-[10px] text-[#909296] border border-[#2c2e33] bg-[#25262b] px-2 py-1 rounded font-mono">
                {labelAgent(agent.agent_id)}: {agent.reason}
              </span>
            ))}
          </div>
        </div>
      )}

      {Array.isArray(agentPlan?.notes) && agentPlan.notes.length > 0 && (
        <div className="text-xs text-[#909296] bg-[#141517] border border-[#2c2e33] rounded p-3">
          {agentPlan.notes.join(" ")}
        </div>
      )}
    </section>
  );
}

function SummaryGrid({ run, artifactsCount, changesCount, commandsCount, modelsCount }: { run: RunResult; artifactsCount: number; changesCount: number; commandsCount: number; modelsCount: number }) {
  const costLabel = run.mode === "mock" ? "Estimated If Live" : "Estimated Cost";
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

function labelAgent(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function labelSearchProvider(value?: string | null): string {
  if (value === "exa_direct") return "Exa Direct";
  if (!value) return "none";
  return value;
}

function formatSearchStatus(value?: string): string {
  return (value || "unknown").replace(/_/g, " ");
}

function searchStatusSentence(log: SearchLogRecord): string {
  if (log.status === "success" && log.mode === "live") return "Live search was executed and sources were stored. Review source quality before public use.";
  if (log.status === "mock_fixture") return "Mock search fixture was used. No paid provider search was made.";
  if (log.status === "skipped") return log.error_message || "Search was unavailable or skipped. No current claims should be made.";
  if (log.status === "failed") return "Search failed. Use the error message and do not make current claims.";
  if (log.status === "cache_hit") return "Cached search evidence was used.";
  return "Search evidence was recorded for this run.";
}
