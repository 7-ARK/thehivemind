import { FileText } from "lucide-react";
import type { RunRecord } from "@/lib/api";

type OutputPanelProps = {
  run?: RunRecord;
};

export function OutputPanel({ run }: OutputPanelProps) {
  return (
    <section className="panel p-5 md:p-6">
      <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-hive-cyan" />
            <p className="fine-label">Final Output</p>
          </div>
          <h2 className="mt-1 text-lg font-semibold text-hive-text">{run ? "Professional run report" : "Report will appear after a run"}</h2>
        </div>
        {run ? (
          <div className="rounded-lg border border-hive-border bg-hive-panelSoft px-3 py-2 text-xs text-hive-muted">
            {run.metrics.total_estimated_tokens.toLocaleString()} tokens - ${run.metrics.total_estimated_cost_usd.toFixed(6)}
          </div>
        ) : null}
      </div>
      {run ? (
        <div className="space-y-4">
          <div className="surface p-5">
            <p className="fine-label">Summary</p>
            <p className="mt-2 text-sm leading-7 text-hive-text">{run.final_output.summary}</p>
          </div>
          <OutputList title="Work completed" items={run.final_output.what_was_done} />
          <OutputList title="Agent contributions" items={run.agents.map((agent) => `${agent.name}: ${agent.latest_action}`)} />
          <OutputList title="Next actions" items={run.final_output.recommended_next_actions} />
          <OutputList title="Generated artifacts/tasks" items={run.final_output.generated_artifacts} />
        </div>
      ) : (
        <p className="surface p-4 text-sm leading-6 text-hive-muted">
          Submit a command to generate a structured final answer, artifacts, and next actions.
        </p>
      )}
    </section>
  );
}

function OutputList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-hive-text">{title}</h3>
      <ul className="mt-2 grid gap-2 sm:grid-cols-2">
        {items.map((item) => (
          <li key={item} className="rounded-lg border border-hive-border bg-hive-panelSoft p-3 text-sm leading-6 text-hive-muted">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
