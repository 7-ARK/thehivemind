import { RunEvent, RunResult } from "../../types";

interface Props {
  run: RunResult;
  events: RunEvent[];
}

export default function RunUsagePanel({ run, events }: Props) {
  const modelSet = new Set<string>();
  events.forEach((event) => modelSet.add(event.model_used));
  run.usage_summary?.models_used?.forEach((model) => modelSet.add(model));
  const models = Array.from(modelSet);
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4">
      <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono mb-3">Usage</h3>
      <div className="grid grid-cols-2 gap-3">
        <Metric label={run.mode === "mock" ? "Estimated If Live" : "Cost"} value={`$${run.metrics.total_estimated_cost_usd.toFixed(6)}`} />
        {run.mode === "mock" && <Metric label="Actual API Cost" value="$0.00" />}
        <Metric label="Tokens" value={run.metrics.total_estimated_tokens.toLocaleString()} />
        <Metric label="Agents" value={String(run.metrics.agents_used)} />
        <Metric label="Tasks" value={String(run.metrics.tasks_completed)} />
      </div>
      {run.mode === "mock" && (
        <p className="mt-3 text-[11px] text-[#20c997]">Mock mode run. No live API credits were used by this run path.</p>
      )}
      {run.mode === "live" && (
        <p className="mt-3 text-[11px] text-[#fab005]">Live mode run. Inspect models, cost, and provider calls before using outputs publicly.</p>
      )}
      <div className="mt-4 space-y-2">
        <h4 className="text-[10px] text-[#909296] uppercase font-mono">{run.mode === "mock" ? "Planned Models" : "Models Used"}</h4>
        {models.length === 0 ? (
          <p className="text-xs text-[#909296]">No model list available.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {models.map((model) => (
              <span key={model} className="bg-[#141517] border border-[#2c2e33] text-[#e9ecef] rounded px-2 py-1 text-[10px] font-mono">
                {model}
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="mt-4 space-y-2">
        <h4 className="text-[10px] text-[#909296] uppercase font-mono">Per-Agent Estimates</h4>
        {events.map((event) => (
          <div key={`${event.agent_name}-${event.timestamp}`} className="bg-[#141517] border border-[#2c2e33] rounded p-2 text-[11px]">
            <div className="flex justify-between gap-3">
              <span className="text-[#e9ecef]">{event.agent_name}</span>
              <span className="text-[#fab005]">{run.mode === "mock" ? "sim " : ""}${event.estimated_cost_usd.toFixed(6)}</span>
            </div>
            <div className="text-[#909296] font-mono mt-1">
              {run.mode === "mock"
                ? `Actual provider: mock / Planned model: ${event.model_used}`
                : `${event.provider ?? "provider n/a"} / ${event.model_used}`} / {(event.estimated_tokens ?? event.estimated_input_tokens + event.estimated_output_tokens).toLocaleString()} tokens
            </div>
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
      <div className="text-xs text-[#e9ecef] font-mono mt-1">{value}</div>
    </div>
  );
}
