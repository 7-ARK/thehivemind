import { FileText } from "lucide-react";
import type { RunRecord } from "@/lib/api";

type OutputPanelProps = {
  run?: RunRecord;
};

export function OutputPanel({ run }: OutputPanelProps) {
  return (
    <section className="panel rounded-lg p-5">
      <div className="mb-4 flex items-center gap-2">
        <FileText className="h-4 w-4 text-hive-teal" />
        <h2 className="text-base font-semibold">Final Output</h2>
      </div>
      {run ? (
        <div className="space-y-4">
          <p className="rounded-md border border-hive-border bg-hive-panelSoft p-4 text-sm leading-6">
            {run.final_output.summary}
          </p>
          <OutputList title="What was done" items={run.final_output.what_was_done} />
          <OutputList title="Next recommended actions" items={run.final_output.recommended_next_actions} />
          <OutputList title="Generated artifacts/tasks" items={run.final_output.generated_artifacts} />
        </div>
      ) : (
        <p className="rounded-md border border-hive-border bg-hive-panelSoft p-4 text-sm text-hive-muted">
          Submit a command to generate a structured final answer, artifacts, and next actions.
        </p>
      )}
    </section>
  );
}

function OutputList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <h3 className="text-sm font-semibold">{title}</h3>
      <ul className="mt-2 grid gap-2 sm:grid-cols-2">
        {items.map((item) => (
          <li key={item} className="rounded-md border border-hive-border bg-hive-panelSoft p-3 text-sm text-hive-muted">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

