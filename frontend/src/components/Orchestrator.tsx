import React, { useEffect, useMemo, useState } from "react";
import { createRun, decideApproval, getProjectChanges, getRunCommands } from "../lib/api";
import { collectRunCommands, collectRunFiles, FileSummaryItem } from "../lib/runSummary";
import { ApprovalRequiredResponse, CommandResult, CreateRunPayload, ProjectChange, RunEvent, RunResult } from "../types";
import MarkdownView from "./MarkdownView";
import ApprovalPanel from "./approvals/ApprovalPanel";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Cpu,
  Database,
  FileText,
  PlayCircle,
  ShieldCheck,
  Terminal,
  ToggleLeft,
  ToggleRight,
} from "lucide-react";

interface OrchestratorProps {
  onWorkflowCompleted: (projectId?: string, runId?: string) => void;
  onOpenProject: (projectId: string) => void;
  onOpenRunDetail: (runId: string, projectId?: string) => void;
}

const EXAMPLE_CREATE = "Create a simple Greek yogurt order website prototype with files.";
const EXAMPLE_CONTINUE = "Continue the Greek yogurt website and add a simple order status page.";

export default function Orchestrator({ onWorkflowCompleted, onOpenProject, onOpenRunDetail }: OrchestratorProps) {
  const [command, setCommand] = useState(EXAMPLE_CREATE);
  const [projectId, setProjectId] = useState("greek-yogurt-test");
  const [mode, setMode] = useState<CreateRunPayload["mode"]>("mock");
  const [runType, setRunType] = useState<CreateRunPayload["run_type"]>("prototype_build");
  const [allowFileWrites, setAllowFileWrites] = useState(true);
  const [allowSafeCommands, setAllowSafeCommands] = useState(true);
  const [allowCeoLive, setAllowCeoLive] = useState(false);
  const [maxCostUsd, setMaxCostUsd] = useState("0.25");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunResult | null>(null);
  const [approvalRequired, setApprovalRequired] = useState<ApprovalRequiredResponse | null>(null);
  const [approvalPayload, setApprovalPayload] = useState<CreateRunPayload | null>(null);
  const [decidingApprovalId, setDecidingApprovalId] = useState<string | null>(null);
  const [resultCommands, setResultCommands] = useState<CommandResult[]>([]);
  const [resultChanges, setResultChanges] = useState<ProjectChange[]>([]);
  const [error, setError] = useState<string | null>(null);

  const payload = useMemo<CreateRunPayload>(
    () => ({
      command: command.trim(),
      mode,
      project_id: projectId.trim() || null,
      run_type: runType,
      allow_file_writes: allowFileWrites,
      allow_safe_commands: allowSafeCommands,
      allow_ceo_live: allowCeoLive,
      max_cost_usd: Number(maxCostUsd) || 0.25,
    }),
    [allowCeoLive, allowFileWrites, allowSafeCommands, command, maxCostUsd, mode, projectId, runType],
  );

  useEffect(() => {
    if (runType !== "provider_test") return;
    setMode("live");
    setAllowFileWrites(false);
    setAllowSafeCommands(false);
    setAllowCeoLive(false);
    setMaxCostUsd("0.01");
  }, [runType]);

  const executeRun = async (runPayload: CreateRunPayload) => {
    if (running || !runPayload.command) return;
    setRunning(true);
    setError(null);
    setResult(null);
    setApprovalRequired(null);
    setResultCommands([]);
    setResultChanges([]);
    try {
      const run = await createRun(runPayload);
      if (run.status === "approval_required") {
        setApprovalRequired(run);
        setApprovalPayload(runPayload);
        return;
      }
      setResult(run);
      const [commandsResult, changesResult] = await Promise.allSettled([
        getRunCommands(run.run_id),
        run.project_id ? getProjectChanges(run.project_id) : Promise.resolve({ project_id: "", changes: [] }),
      ]);
      if (commandsResult.status === "fulfilled") setResultCommands(commandsResult.value);
      if (changesResult.status === "fulfilled") {
        setResultChanges(changesResult.value.changes.filter((change) => change.run_id === run.run_id));
      }
      onWorkflowCompleted(run.project_id ?? runPayload.project_id ?? undefined, run.run_id);
    } catch (err: any) {
      setError(normalizeError(err?.message));
    } finally {
      setRunning(false);
    }
  };

  const handleRun = () => executeRun(payload);

  const handleApprovalDecision = async (approvalId: string, decision: "approved" | "rejected") => {
    if (!approvalRequired) return;
    setDecidingApprovalId(approvalId);
    setError(null);
    try {
      const updated = await decideApproval(approvalId, decision, decision === "approved" ? "Approved from Command Console." : "Rejected from Command Console.");
      setApprovalRequired({
        ...approvalRequired,
        approval_requests: approvalRequired.approval_requests.map((approval) => (approval.id === approvalId ? updated : approval)),
      });
    } catch (err: any) {
      setError(normalizeError(err?.message));
    } finally {
      setDecidingApprovalId(null);
    }
  };

  const handleRunWithApproval = () => {
    if (!approvalRequired || !approvalPayload) return;
    const approvedIds = approvalRequired.approval_requests.filter((approval) => approval.status === "approved").map((approval) => approval.id);
    executeRun({ ...approvalPayload, approval_ids: approvedIds });
  };

  const fileSummary = result ? collectRunFiles(result, resultChanges) : { created: [], updated: [] };
  const commandsRun = result ? collectRunCommands(result, resultCommands) : [];

  return (
    <div id="orchestrator" className="space-y-6">
      <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5">
        <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-4 border-b border-[#2c2e33] pb-4">
          <div>
            <h2 className="text-base font-semibold text-[#e9ecef] flex items-center gap-2">
              <Cpu className="text-[#20c997] w-4 h-4" />
              <span>Command Console v2</span>
            </h2>
            <p className="text-xs text-[#909296] mt-1 max-w-2xl">
              Start controlled backend runs with explicit project, mode, safety, and cost settings.
            </p>
          </div>
          <div className="flex flex-wrap gap-2 text-[10px] font-mono">
            <Badge tone={mode === "mock" ? "green" : "amber"}>{mode === "mock" ? "MOCK SAFE" : "LIVE GUARDED"}</Badge>
            <Badge tone={allowCeoLive ? "amber" : "green"}>{allowCeoLive ? "CEO LIVE ON" : "GPT-5.5 BLOCKED"}</Badge>
            <Badge tone="neutral">MAX ${payload.max_cost_usd.toFixed(2)}</Badge>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-5">
          <div className="space-y-4">
            <div>
              <label className="text-[10px] text-[#909296] font-mono uppercase tracking-wider font-bold">
                Command
              </label>
              <textarea
                id="orchestration-input"
                value={command}
                onChange={(event) => setCommand(event.target.value)}
                disabled={running}
                placeholder="Tell TheHiveMind what to build, research, automate, or continue..."
                className="mt-2 min-h-32 w-full bg-[#141517] border border-[#2c2e33] rounded text-[#e9ecef] text-sm px-3.5 py-3 outline-none focus:ring-1 focus:ring-[#20c997]/60 resize-y"
              />
              <p className="mt-2 text-[10px] text-[#909296] leading-relaxed">
                Risky requests in text are detected, but typing them is not approval. Live mode, GPT-5.5, deploys, installs, payments, and external actions require approval cards.
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <ExampleButton onClick={() => setCommand(EXAMPLE_CREATE)}>Create Greek yogurt website prototype</ExampleButton>
                <ExampleButton onClick={() => setCommand(EXAMPLE_CONTINUE)}>Continue and add order status page</ExampleButton>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
              <Field label="Project ID" helper="Same project ID = continue existing project. New project ID = start a new workspace.">
                <input
                  value={projectId}
                  onChange={(event) => setProjectId(event.target.value)}
                  disabled={running}
                  className="control-input"
                />
              </Field>

              <Field label="Mode" helper={mode === "mock" ? "Mock mode uses deterministic responses and does not spend API credits." : "Live mode can use real API credits. Cost guards still apply."}>
                <select value={mode} onChange={(event) => setMode(event.target.value as CreateRunPayload["mode"])} disabled={running} className="control-input">
                  <option value="mock">mock</option>
                  <option value="live">live</option>
                </select>
              </Field>

              <Field label="Run Type" helper="provider_test runs one tiny live call with no files or commands; prototype_build and continuation use project files.">
                <select value={runType} onChange={(event) => setRunType(event.target.value as CreateRunPayload["run_type"])} disabled={running} className="control-input">
                  <option value="provider_test">provider_test</option>
                  <option value="prototype_build">prototype_build</option>
                  <option value="business_launch_plan">business_launch_plan</option>
                  <option value="continuation">continuation</option>
                </select>
              </Field>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-4 gap-3">
              <ToggleControl label="Allow file writes" checked={allowFileWrites} onChange={setAllowFileWrites} disabled={running} />
              <ToggleControl label="Allow safe commands" checked={allowSafeCommands} onChange={setAllowSafeCommands} disabled={running} />
              <ToggleControl
                label="Allow CEO live model"
                checked={allowCeoLive}
                onChange={setAllowCeoLive}
                disabled={running}
                warning="GPT-5.5 may be expensive. Keep this off unless needed."
              />
              <Field label="Max run cost" helper="The run should stop if estimated cost crosses this limit.">
                <input
                  value={maxCostUsd}
                  onChange={(event) => setMaxCostUsd(event.target.value)}
                  disabled={running}
                  type="number"
                  min="0.01"
                  max="5"
                  step="0.01"
                  className="control-input"
                />
              </Field>
            </div>

            {mode === "live" ? (
              <WarningCard>
                Live mode can use real API credits. GPT-5.5 remains blocked unless CEO live is enabled. Current cost limit: ${payload.max_cost_usd.toFixed(2)}.
              </WarningCard>
            ) : (
              <InfoCard>Mock mode uses deterministic responses and does not spend API credits.</InfoCard>
            )}

            {error && <ErrorCard>{error}</ErrorCard>}

            {approvalRequired && (
              <ApprovalPanel
                approvals={approvalRequired.approval_requests}
                decidingId={decidingApprovalId}
                onDecision={handleApprovalDecision}
                onRunWithApproval={handleRunWithApproval}
              />
            )}

            <button
              id="run-orchestration-btn"
              onClick={handleRun}
              disabled={running || !payload.command}
              className="bg-[#20c997] hover:bg-[#1db184] disabled:bg-[#2c2e33] disabled:text-[#909296] text-[#141517] text-sm font-bold px-4 py-3 rounded flex items-center justify-center gap-2 transition-all outline-none cursor-pointer w-full sm:w-auto"
            >
              <PlayCircle className={`w-4 h-4 ${running ? "animate-spin" : ""}`} />
              {running ? "Running Hive..." : "Run Hive"}
            </button>
          </div>

          <PayloadPreview payload={payload} />
        </div>
      </section>

      {result && (
        <section className="grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-6">
          <div className="space-y-6">
            <RunResultPanel
              result={result}
              filesCreated={fileSummary.created}
              filesUpdated={fileSummary.updated}
              commandsRun={commandsRun}
              onOpenProject={() => result.project_id && onOpenProject(result.project_id)}
              onOpenRunDetail={() => onOpenRunDetail(result.run_id, result.project_id ?? undefined)}
            />
            <Timeline events={result.events} mode={result.mode} />
            <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5">
              <h3 className="text-xs font-bold text-[#909296] tracking-wider uppercase flex items-center gap-2 mb-3">
                <FileText className="w-4 h-4 text-[#20c997]" />
                Final Report
              </h3>
              <div className="bg-[#141517] border border-[#2c2e33] rounded p-4">
                <MarkdownView content={buildFinalReport(result)} />
              </div>
            </section>
          </div>

          <aside className="space-y-6">
            <ListCard title="Files Created" items={fileSummary.created.map(formatFileSummary)} empty="No project files created in this run." />
            <ListCard title="Files Updated" items={fileSummary.updated.map(formatFileSummary)} empty="No project files updated in this run." />
            <CommandCard commands={commandsRun} />
            <ListCard title="Artifacts" items={result.artifacts.map((artifact) => `${artifact.name} [${artifact.type}]`)} empty="No artifacts returned." />
          </aside>
        </section>
      )}
    </div>
  );
}

function Field({ label, helper, children }: { label: string; helper: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[10px] text-[#909296] font-mono uppercase tracking-wider font-bold">{label}</span>
      <div className="mt-2">{children}</div>
      <span className="mt-1.5 block text-[10px] text-[#909296] leading-relaxed">{helper}</span>
    </label>
  );
}

function ToggleControl({ label, checked, onChange, disabled, warning }: { label: string; checked: boolean; onChange: (value: boolean) => void; disabled?: boolean; warning?: string }) {
  return (
    <div className="bg-[#141517] border border-[#2c2e33] rounded p-3">
      <button
        type="button"
        onClick={() => onChange(!checked)}
        disabled={disabled}
        className="w-full flex items-center justify-between gap-3 text-left"
      >
        <span className="text-xs font-semibold text-[#e9ecef]">{label}</span>
        {checked ? <ToggleRight className="w-5 h-5 text-[#20c997]" /> : <ToggleLeft className="w-5 h-5 text-[#909296]" />}
      </button>
      {warning && <p className="mt-2 text-[10px] text-[#fab005] leading-relaxed">{warning}</p>}
    </div>
  );
}

function ExampleButton({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <button onClick={onClick} className="text-[10px] bg-[#25262b] hover:bg-[#2c2e33] text-[#909296] hover:text-[#e9ecef] border border-[#2c2e33] px-2.5 py-1 rounded transition-colors">
      {children}
    </button>
  );
}

function PayloadPreview({ payload }: { payload: CreateRunPayload }) {
  return (
    <div className="bg-[#141517] border border-[#2c2e33] rounded-lg p-4 h-fit">
      <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono mb-3 flex items-center gap-2">
        <Terminal className="w-4 h-4 text-[#20c997]" />
        Payload
      </h3>
      <pre className="text-[11px] text-[#909296] whitespace-pre-wrap font-mono leading-relaxed">{JSON.stringify(payload, null, 2)}</pre>
    </div>
  );
}

function RunResultPanel({
  result,
  filesCreated,
  filesUpdated,
  commandsRun,
  onOpenProject,
  onOpenRunDetail,
}: {
  result: RunResult;
  filesCreated: FileSummaryItem[];
  filesUpdated: FileSummaryItem[];
  commandsRun: CommandResult[];
  onOpenProject: () => void;
  onOpenRunDetail: () => void;
}) {
  const costLabel = result.mode === "mock" ? "Estimated if live" : "Cost";
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5">
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4">
        <div>
          <h3 className="text-sm font-bold text-[#e9ecef] flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-[#20c997]" />
            Run Completed
          </h3>
          <p className="text-xs text-[#909296] mt-1">{result.final_output.summary}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={onOpenRunDetail} className="bg-[#20c997] hover:bg-[#1db184] text-[#141517] px-3 py-2 rounded text-xs font-bold flex items-center gap-2">
            <Terminal className="w-4 h-4" />
            View Run Details
          </button>
          {result.project_id && (
            <button onClick={onOpenProject} className="bg-[#25262b] hover:bg-[#2c2e33] border border-[#2c2e33] text-[#20c997] px-3 py-2 rounded text-xs font-bold flex items-center gap-2">
              <Database className="w-4 h-4" />
              View Project Workspace
            </button>
          )}
        </div>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-4">
        <Metric label="Run ID" value={result.run_id.slice(0, 8)} />
        <Metric label="Status" value={result.status} />
        <Metric label="Mode" value={result.mode} />
        <Metric label="Run Type" value={result.run_type} />
        <Metric label={costLabel} value={`$${result.metrics.total_estimated_cost_usd.toFixed(6)}`} />
        {result.mode === "mock" && <Metric label="Actual API Cost" value="$0.00" />}
        <Metric label="Agents" value={String(result.metrics.agents_used)} />
        <Metric label="Created" value={String(filesCreated.length)} />
        <Metric label="Updated" value={String(filesUpdated.length)} />
        <Metric label="Commands" value={String(commandsRun.length)} />
        <Metric label="Memory Updates" value={String(result.memory_updates?.length ?? 0)} />
      </div>
    </section>
  );
}

function Timeline({ events, mode }: { events: RunEvent[]; mode: RunResult["mode"] }) {
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5">
      <h3 className="text-xs font-bold text-[#909296] tracking-wider uppercase mb-4 flex items-center gap-2">
        <Terminal className="w-4 h-4 text-[#20c997]" />
        Timeline
      </h3>
      <div className="space-y-3">
        {events.map((event, index) => (
          <div key={`${event.agent_name}-${index}`} className="bg-[#25262b] border border-[#2c2e33] rounded p-3">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <div>
                <span className="text-[10px] text-[#20c997] font-mono uppercase">Step {index + 1}</span>
                <h4 className="text-xs font-bold text-[#e9ecef]">{event.agent_name}</h4>
              </div>
              <div className="flex flex-wrap gap-2 text-[10px] font-mono text-[#909296]">
                <span>{event.status}</span>
                {mode === "mock" ? (
                  <>
                    <span>Actual provider: mock</span>
                    <span>Planned model: {event.model_used}</span>
                    <span className="text-[#fab005]">sim ${event.estimated_cost_usd.toFixed(6)}</span>
                  </>
                ) : (
                  <>
                    <span>{event.provider ?? "provider n/a"}</span>
                    <span>{event.model_used}</span>
                    <span className="text-[#fab005]">${event.estimated_cost_usd.toFixed(6)}</span>
                  </>
                )}
              </div>
            </div>
            <p className="text-xs text-[#909296] mt-2">{event.action_summary}</p>
            {event.artifact_id && <p className="text-[10px] text-[#20c997] font-mono mt-2">artifact: {event.artifact_id}</p>}
          </div>
        ))}
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-[#141517] border border-[#2c2e33] rounded p-3">
      <div className="text-[10px] text-[#909296] uppercase font-mono">{label}</div>
      <div className="text-xs text-[#e9ecef] font-mono mt-1 truncate">{value}</div>
    </div>
  );
}

function ListCard({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4">
      <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono mb-3">{title}</h3>
      {items.length === 0 ? (
        <p className="text-xs text-[#909296]">{empty}</p>
      ) : (
        <div className="space-y-2 max-h-72 overflow-auto">
          {items.map((item) => (
            <div key={item} className="bg-[#141517] border border-[#2c2e33] rounded p-2 text-[11px] text-[#e9ecef] font-mono break-all">
              {item}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function CommandCard({ commands }: { commands: RunResult["commands_run"] }) {
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4">
      <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono mb-3">Commands Run</h3>
      {commands.length === 0 ? (
        <p className="text-xs text-[#909296]">No commands recorded.</p>
      ) : (
        <div className="space-y-2">
          {commands.map((command, index) => (
            <div key={index} className="bg-[#141517] border border-[#2c2e33] rounded p-2 text-[11px]">
              <code className="text-[#e9ecef] break-all">{command.command.join(" ")}</code>
              <div className={command.exit_code === 0 ? "text-[#20c997] mt-1" : "text-[#fab005] mt-1"}>exit {command.exit_code}</div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function formatFileSummary(item: FileSummaryItem): string {
  const detail = item.summary ? ` - ${item.summary}` : "";
  return `${item.path}${detail}`;
}

function WarningCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-[#fab005]/10 border border-[#fab005]/30 text-[#fab005] p-3 rounded text-xs flex gap-2">
      <AlertTriangle className="w-4 h-4 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

function InfoCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-[#20c997]/10 border border-[#20c997]/20 text-[#20c997] p-3 rounded text-xs flex gap-2">
      <ShieldCheck className="w-4 h-4 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

function ErrorCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-rose-500/10 border border-rose-500/30 text-rose-300 p-3 rounded text-xs flex gap-2">
      <AlertTriangle className="w-4 h-4 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

function Badge({ children, tone }: { children: React.ReactNode; tone: "green" | "amber" | "neutral" }) {
  const color = tone === "green" ? "text-[#20c997] border-[#20c997]/20 bg-[#20c997]/10" : tone === "amber" ? "text-[#fab005] border-[#fab005]/30 bg-[#fab005]/10" : "text-[#909296] border-[#2c2e33] bg-[#25262b]";
  return <span className={`px-2 py-1 rounded border ${color}`}>{children}</span>;
}

function buildFinalReport(run: RunResult): string {
  const work = run.final_output.what_was_done.map((item) => `- ${item}`).join("\n");
  const next = run.final_output.recommended_next_actions.map((item) => `- ${item}`).join("\n");
  return `### ${run.command}

**Run ID:** \`${run.run_id}\`
**Status:** ${run.status}
**Project:** ${run.project_id ?? "unassigned"}
**Mode:** ${run.mode}

#### Summary
${run.final_output.summary}

#### Work Completed
${work}

#### Next Actions
${next}`;
}

function normalizeError(message?: string): string {
  if (!message) return "Unknown backend error.";
  if (message.includes("Live provider calls are disabled")) return "Live calls are disabled in the backend. Keep mock mode on or enable ALLOW_LIVE_CALLS=true.";
  if (message.includes("API key is not configured")) return "The selected live provider is missing an API key.";
  if (message.includes("max_cost_usd") || message.includes("cost")) return message;
  if (message.includes("allow_file_writes")) return "This run type needs file writes enabled.";
  return message;
}
