import { Clock, Database, DollarSign, ListChecks, Network, Sigma } from "lucide-react";
import type { RunRecord } from "@/lib/api";

type MetricsPanelProps = {
  run?: RunRecord;
};

export function MetricsPanel({ run }: MetricsPanelProps) {
  const totalTokens = run?.metrics.total_estimated_tokens ?? 0;
  const completedTasks = run?.metrics.tasks_completed ?? 0;
  const expectedTasks = 7;
  const completionPct = Math.min(100, Math.round((completedTasks / expectedTasks) * 100));
  const maxAgentCost = Math.max(...(run?.events.map((event) => event.estimated_cost_usd) ?? [0.000001]));
  const metrics = [
    {
      label: "Estimated tokens",
      value: run?.metrics.total_estimated_tokens.toLocaleString() ?? "0",
      icon: Sigma
    },
    {
      label: "Estimated cost",
      value: `$${(run?.metrics.total_estimated_cost_usd ?? 0).toFixed(6)}`,
      icon: DollarSign
    },
    {
      label: "Agents used",
      value: String(run?.metrics.agents_used ?? 0),
      icon: Network
    },
    {
      label: "Tasks completed",
      value: String(run?.metrics.tasks_completed ?? 0),
      icon: ListChecks
    },
    {
      label: "Run duration",
      value: `${run?.metrics.run_duration_seconds ?? 0}s`,
      icon: Clock
    },
    {
      label: "Memory chunks",
      value: String(run?.metrics.memory_chunks_retrieved ?? 0),
      icon: Database
    }
  ];

  return (
    <section id="metrics" className="panel p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="fine-label">Run Overview</p>
          <h2 className="mt-1 text-lg font-semibold text-hive-text">{run ? "Completed mock orchestration" : "Waiting for first run"}</h2>
        </div>
        <span className="rounded-full border border-hive-border bg-hive-panelSoft px-3 py-1 text-xs text-hive-muted">
          {run?.status ?? "idle"}
        </span>
      </div>
      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {metrics.map(({ label, value, icon: Icon }) => (
          <div key={label} className="metric-card p-4">
            <div className="flex items-center gap-2 text-xs text-hive-muted">
              <Icon className="h-3.5 w-3.5" />
              {label}
            </div>
            <div className="mt-2 text-xl font-semibold text-hive-text">{value}</div>
          </div>
        ))}
      </div>
      <div className="mt-5 grid gap-3 lg:grid-cols-3">
        <MiniBar title="Token usage" label={`${totalTokens.toLocaleString()} estimated`} value={Math.min(100, totalTokens / 12)} />
        <MiniBar title="Task completion" label={`${completedTasks}/${expectedTasks} workflow steps`} value={completionPct} tone="green" />
        <div className="surface p-4">
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm font-medium text-hive-text">Cost by agent</span>
            <span className="text-xs text-hive-muted">actual run events</span>
          </div>
          <div className="mt-3 space-y-2">
            {(run?.events ?? []).slice(0, 5).map((event) => (
              <div key={`${event.agent_name}-${event.timestamp}`} className="grid grid-cols-[105px_1fr_auto] items-center gap-2 text-xs">
                <span className="truncate text-hive-muted">{event.agent_name.replace(" Agent", "")}</span>
                <div className="h-1.5 overflow-hidden rounded-full bg-hive-shell">
                  <div
                    className="h-full rounded-full bg-hive-amber"
                    style={{ width: `${Math.max(6, (event.estimated_cost_usd / maxAgentCost) * 100)}%` }}
                  />
                </div>
                <span className="text-hive-muted">${event.estimated_cost_usd.toFixed(6)}</span>
              </div>
            ))}
            {!run ? <p className="text-xs text-hive-muted">Cost allocation appears after a run.</p> : null}
          </div>
        </div>
      </div>
    </section>
  );
}

function MiniBar({ title, label, value, tone = "amber" }: { title: string; label: string; value: number; tone?: "amber" | "green" }) {
  return (
    <div className="surface p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-hive-text">{title}</span>
        <span className="text-xs text-hive-muted">{label}</span>
      </div>
      <div className="mt-4 h-2 overflow-hidden rounded-full bg-hive-shell">
        <div
          className={tone === "green" ? "h-full rounded-full bg-hive-green" : "h-full rounded-full bg-hive-amber"}
          style={{ width: `${Math.max(3, Math.min(100, value))}%` }}
        />
      </div>
    </div>
  );
}
