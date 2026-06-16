import { CheckCircle2, CircleDashed } from "lucide-react";
import type { RunEvent } from "@/lib/api";

type RunTimelineProps = {
  events: RunEvent[];
};

const emptySteps = ["CEO Planning", "Model Selection", "Research", "Coding", "Content", "QA Review", "Final Output"];

export function RunTimeline({ events }: RunTimelineProps) {
  return (
    <section className="panel rounded-lg p-5">
      <h2 className="text-base font-semibold">Run Timeline</h2>
      <div className="mt-5 space-y-4">
        {events.length === 0
          ? emptySteps.map((step) => (
              <div key={step} className="flex gap-3">
                <CircleDashed className="mt-0.5 h-5 w-5 text-hive-muted" />
                <div>
                  <div className="text-sm font-medium text-hive-text">{step}</div>
                  <p className="text-sm text-hive-muted">Waiting for a command.</p>
                </div>
              </div>
            ))
          : events.map((event) => (
              <div key={`${event.timestamp}-${event.agent_name}`} className="relative flex gap-3">
                <CheckCircle2 className="mt-0.5 h-5 w-5 text-hive-teal" />
                <div className="w-full rounded-md border border-hive-border bg-hive-panelSoft p-3">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <div className="text-sm font-semibold">{event.agent_name}</div>
                      <p className="text-xs text-hive-muted">{event.action_summary}</p>
                    </div>
                    <div className="flex flex-wrap gap-2 text-xs">
                      <span className="rounded bg-hive-bg px-2 py-1 text-hive-muted">{event.model_used}</span>
                      <span className="rounded bg-hive-bg px-2 py-1 text-hive-accent">
                        ${event.estimated_cost_usd.toFixed(6)}
                      </span>
                    </div>
                  </div>
                  <p className="mt-3 text-sm text-hive-text">{event.output_summary}</p>
                </div>
              </div>
            ))}
      </div>
    </section>
  );
}

