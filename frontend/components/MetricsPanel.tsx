import { Clock, Database, DollarSign, ListChecks, Network, Sigma } from "lucide-react";
import type { RunRecord } from "@/lib/api";

type MetricsPanelProps = {
  run?: RunRecord;
};

export function MetricsPanel({ run }: MetricsPanelProps) {
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
    <section className="panel rounded-lg p-5">
      <h2 className="text-base font-semibold">Metrics</h2>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {metrics.map(({ label, value, icon: Icon }) => (
          <div key={label} className="rounded-md border border-hive-border bg-hive-panelSoft p-3">
            <div className="flex items-center gap-2 text-xs text-hive-muted">
              <Icon className="h-3.5 w-3.5" />
              {label}
            </div>
            <div className="mt-2 text-xl font-semibold">{value}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

