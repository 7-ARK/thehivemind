import React, { useState } from "react";
import { submitOrchestration } from "../lib/api";
import { OrchestrationResult, CompletedAgentStep } from "../types";
import MarkdownView from "./MarkdownView";
import {
  Terminal,
  Cpu,
  PlayCircle,
  Database,
  Search,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  Zap,
  Layers,
  ArrowRight,
  Clock
} from "lucide-react";

interface OrchestratorProps {
  onWorkflowCompleted: () => void; // Trigger callback to notify parent stats were updated!
}

export default function Orchestrator({ onWorkflowCompleted }: OrchestratorProps) {
  const [command, setCommand] = useState("Build a launch plan for a Greek yogurt business");
  const [running, setRunning] = useState(false);
  const [currentStepIndex, setCurrentStepIndex] = useState(-1);
  const [accumulatedSteps, setAccumulatedSteps] = useState<CompletedAgentStep[]>([]);
  const [result, setResult] = useState<OrchestrationResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Preset quick commands for recruiters
  const presets = [
    "Build a launch plan for a Greek yogurt business",
    "Develop high-performance trading bot on Rust",
    "Create a multiagent workspace calendar assistant integration",
  ];

  const handleRun = async () => {
    if (running || !command.trim()) return;

    setRunning(true);
    setError(null);
    setResult(null);
    setCurrentStepIndex(0);
    setAccumulatedSteps([]);

    try {
      // 1. Submit to Express simulation backend
      const res = await submitOrchestration(command);

      // 2. Play active step intervals to simulate AI thinking times for recruiters!
      for (let i = 0; i < res.agentSteps.length; i++) {
        setCurrentStepIndex(i);
        setAccumulatedSteps((prev) => [...prev, res.agentSteps[i]]);
        // Allow thinking gaps
        await new Promise((resolve) => setTimeout(resolve, 1400));
      }

      // 3. Mark complete and store the final output payload
      setResult(res);
      setCurrentStepIndex(res.agentSteps.length);
      
      // Notify parent to trigger a statistics re-fetch
      onWorkflowCompleted();
    } catch (e: any) {
      setError(e.message || "Failed to reach agent orchestrator backend cluster.");
    } finally {
      setRunning(false);
    }
  };

  const currentAgent = running && currentStepIndex >= 0 && currentStepIndex < 5 
    ? ["CEO Agent", "Model Selector", "Research Agent", "Coding Agent", "QA Agent"][currentStepIndex] 
    : null;

  return (
    <div id="orchestrator" className="space-y-6">
      {/* Visual branding banner */}
      <div className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5 relative overflow-hidden">
        <div className="absolute right-0 top-0 translate-x-12 -translate-y-12 w-32 h-32 rounded-full bg-[#20c997]/5 blur-[60px] pointer-events-none" />
        <h2 className="text-base font-semibold text-[#e9ecef] flex items-center gap-1.5">
          <Cpu className="text-[#20c997] w-4 h-4" />
          <span>Multiagent Command Console</span>
        </h2>
        <p className="text-xs text-[#909296] mt-1 max-w-xl">
          Dispatch cross-functional assignments. Watch the CEO Planner delegate sub-tasks to model selector, researchers, designers, and QA validations dynamically.
        </p>

        {/* Input box */}
        <div className="mt-4 flex gap-2">
          <input
            id="orchestration-input"
            type="text"
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            disabled={running}
            placeholder="Type a high-level corporate prompt..."
            className="flex-1 bg-[#141517] border border-[#2c2e33] rounded text-[#e9ecef] text-xs sm:text-sm px-3.5 py-2.5 outline-none focus:ring-1 focus:ring-[#20c997]/60 transition-all font-sans"
          />
          <button
            id="run-orchestration-btn"
            onClick={handleRun}
            disabled={running || !command.trim()}
            className="bg-[#20c997] hover:bg-[#1db184] disabled:bg-[#2c2e33] disabled:text-[#909296] text-[#141517] text-xs sm:text-sm font-bold px-4 py-2.5 rounded flex items-center gap-1.5 transition-all outline-none cursor-pointer"
          >
            <PlayCircle className={`w-4.5 h-4.5 ${running ? "animate-spin text-[#141517]" : ""}`} />
            {running ? "Orchestrating..." : "Run Hive"}
          </button>
        </div>

        {/* Presets */}
        <div className="mt-3.5 flex flex-wrap items-center gap-2">
          <span className="text-[10px] text-[#909296] font-medium font-sans">Quick Presets:</span>
          {presets.map((p, idx) => (
            <button
              key={idx}
              id={`preset-btn-${idx}`}
              onClick={() => setCommand(p)}
              disabled={running}
              className="text-[10px] bg-[#25262b] hover:bg-[#2c2e33] text-[#909296] hover:text-[#e9ecef] border border-[#2c2e33] px-2.5 py-1 rounded transition-colors truncate max-w-[200px]"
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="bg-rose-500/5 border border-rose-500/20 text-rose-300 p-4 rounded-xl text-xs flex items-center gap-2.5 font-sans">
          <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Running pipelines / workflow diagram */}
      {(running || result) && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Timeline and Active Logs */}
          <div className="lg:col-span-2 space-y-6">
            <div className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5">
              <h3 className="text-xs font-[#fab005] font-bold text-[#909296] tracking-wider uppercase mb-4 flex items-center gap-2">
                <Terminal className="w-4 h-4 text-[#20c997]" />
                Live Agent Task Stream
              </h3>

              {/* Steps checklist */}
              <div className="space-y-4">
                {accumulatedSteps.map((step, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 bg-[#25262b] rounded-lg border border-[#2c2e33] flex items-start gap-3 relative overflow-hidden"
                  >
                    <div className="p-1 px-1.5 bg-[#141517] border border-[#2c2e33] rounded text-[9px] font-mono text-[#20c997] font-bold uppercase select-none shrink-0 mt-0.5">
                      STEP {idx + 1}
                    </div>

                    <div className="flex-1 space-y-1">
                      <div className="flex items-center justify-between text-xs font-semibold">
                        <span className="text-[#e9ecef]">{step.agent}</span>
                        <div className="flex items-center gap-2 text-[10px] font-mono text-[#909296]">
                          <span>{step.tokens.toLocaleString()} tokens</span>
                          <span>·</span>
                          <span className="text-[#fab005] font-semibold">${step.cost.toFixed(4)}</span>
                        </div>
                      </div>
                      <p className="text-[10px] text-[#909296] font-mono italic">{step.action}</p>
                      <p className="text-xs text-[#e9ecef]/90 leading-relaxed font-sans mt-1.5">{step.content}</p>
                    </div>
                  </div>
                ))}

                {/* Loading state placeholders */}
                {running && currentStepIndex < 5 && (
                  <div className="p-4 bg-[#25262b]/40 border border-dashed border-[#2c2e33] rounded-lg flex items-center justify-center gap-2.5 py-8 animate-pulse text-xs text-[#909296]">
                    <Zap className="w-4 h-4 text-[#20c997] animate-bounce" />
                    <span>
                      {currentAgent} preparing calculations...
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Generated Report Output details */}
            {result && (
              <div className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5">
                <div className="flex items-center justify-between border-b border-[#2c2e33] pb-3 mb-4">
                  <h3 className="text-xs font-bold text-[#909296] tracking-wider uppercase flex items-center gap-1.5">
                    <Layers className="w-4 h-4 text-[#20c997]" />
                    Orchestrated Output Dispatch
                  </h3>
                  <span className="text-[10px] text-[#20c997] bg-[#20c997]/10 border border-[#20c997]/20 px-2.5 py-0.5 rounded font-mono font-bold">
                    STATUS: DISPATCH_SUCCESS
                  </span>
                </div>

                <div className="bg-[#141517] p-4 rounded border border-[#2c2e33]">
                  <MarkdownView content={result.finalReport} />
                </div>
              </div>
            )}
          </div>

          {/* Side Overview Cards panel */}
          <div className="space-y-6">
            {/* Active Run Telemetry */}
            <div className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5">
              <h3 className="text-xs font-bold text-[#909296] tracking-wider uppercase mb-3">
                Run Context Variables
              </h3>

              <div className="space-y-3.5 border-b border-[#2c2e33] pb-3.5 text-xs">
                <div>
                  <span className="text-[10px] text-[#909296] block uppercase font-bold tracking-wider font-mono">Orchestration Cluster ID</span>
                  <span className="text-xs text-[#e9ecef] font-mono font-semibold">{result?.runId || "Pending deployment..."}</span>
                </div>
                <div>
                  <span className="text-[10px] text-[#909296] block uppercase font-bold tracking-wider font-mono">Elapsed Spends (USD)</span>
                  <span className="text-sm text-[#fab005] font-mono font-bold">${result ? result.cost.toFixed(4) : accumulatedSteps.reduce((acc, step) => acc + step.cost, 0).toFixed(4)}</span>
                </div>
                <div>
                  <span className="text-[10px] text-[#909296] block uppercase font-bold tracking-wider font-mono">Accumulated Tokens</span>
                  <span className="text-xs text-[#20c997] font-mono font-semibold">{result ? `${(result.tokensUsed / 1000).toFixed(1)}K` : `${(accumulatedSteps.reduce((acc, step) => acc + step.tokens, 0) / 1000).toFixed(1)}K`}</span>
                </div>
              </div>

              {/* Memory snippets */}
              <div className="pt-3">
                <span className="text-[10px] text-[#909296] block uppercase font-bold font-mono mb-1.5">RAG context activated</span>
                <p className="text-[11px] text-[#909296] leading-normal mb-2.5">
                  The CEO retrieved relevant memory segments for this command avoiding blind inference:
                </p>
                <div className="space-y-2">
                  {(result?.memoryUsed?.snippets || [
                    "[RAG Search]: Resolving contextual constraints...",
                    "[RAG Search]: Reading document corpus...",
                  ]).map((snip, idx) => (
                    <div key={idx} className="bg-[#141517] border border-[#2c2e33] p-2 rounded text-[10px] text-[#909296] font-mono leading-relaxed truncate">
                      {snip}
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Next actions suggestion block */}
            {result && result.nextActions && (
              <div className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5">
                <h3 className="text-xs font-bold text-[#909296] tracking-wider uppercase mb-3">
                  Autonomous Next Action Triggers
                </h3>
                <div className="space-y-2.5">
                  {result.nextActions.map((act, idx) => (
                    <div key={idx} className="flex gap-2 text-xs text-[#e9ecef]">
                      <ArrowRight className="w-3.5 h-3.5 mt-0.5 text-[#20c997] shrink-0" />
                      <span className="text-[#909296] hover:text-[#e9ecef] transition-colors">{act}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
