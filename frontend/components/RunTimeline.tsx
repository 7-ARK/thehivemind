import { CheckCircle2, CircleDashed } from "lucide-react";
import type { RunEvent } from "@/lib/api";

type RunTimelineProps = {
  events: RunEvent[];
};

const emptySteps = ["Command", "CEO Plan", "Model Selection", "Worker Tasks", "Agent Outputs", "QA Review", "Final Output"];

function stepName(event: RunEvent, index: number) {
  if (event.agent_name === "TheHiveMind") return "Final Output";
  if (event.agent_name === "CEO Agent") return "CEO Plan";
  if (event.agent_name === "Model Selector Agent") return "Model Selection";
  if (["Research Agent", "Coding Agent", "Content Agent"].includes(event.agent_name)) return index === 2 ? "Worker Tasks" : "Agent Outputs";
  if (event.agent_name === "QA Agent") return "QA Review";
  return event.agent_name;
}

export function RunTimeline({ events }: RunTimelineProps) {
  return (
    <section id="timeline" className="panel p-5">
      <div>
        <p className="fine-label">Run Timeline</p>
        <h2 className="mt-1 text-lg font-semibold text-hive-text">Step-by-step execution</h2>
        <p className="mt-2 text-sm leading-6 text-hive-muted">
          Practical work logs only: what happened, who handled it, which model was used, and the estimated cost.
        </p>
      </div>
      <div className="mt-5 space-y-3">
        {events.length === 0
          ? emptySteps.map((step, index) => (
              <div key={step} className="flex gap-3 rounded-lg border border-hive-border bg-hive-panelSoft p-3">
                <CircleDashed className="mt-0.5 h-5 w-5 text-hive-faint" />
                <div>
                  <div className="text-sm font-medium text-hive-text">
                    {index + 1}. {step}
                  </div>
                  <p className="text-sm text-hive-muted">Waiting for a command.</p>
                </div>
              </div>
            ))
          : events.map((event, index) => (
              <div key={`${event.timestamp}-${event.agent_name}`} className="relative flex gap-3">
                <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-hive-border bg-hive-panelSoft">
                  <CheckCircle2 className="h-4 w-4 text-hive-green" />
                </div>
                <div className="w-full rounded-lg border border-hive-border bg-hive-panelSoft p-4">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-hive-text">
                          {index + 1}. {stepName(event, index)}
                        </span>
                        <span className="rounded-full bg-hive-green/10 px-2 py-0.5 text-[11px] text-hive-green">{event.status}</span>
                      </div>
                      <p className="mt-1 text-xs text-hive-muted">{event.agent_name} - {event.agent_role}</p>
                    </div>
                    <div className="flex flex-wrap gap-2 text-xs">
                      <span className="rounded-md bg-hive-shell px-2 py-1 text-hive-muted">{event.model_used}</span>
                      <span className="rounded-md bg-hive-shell px-2 py-1 text-hive-amber">
                        ${event.estimated_cost_usd.toFixed(6)}
                      </span>
                    </div>
                  </div>
                  <div className="mt-3 grid gap-3 text-sm md:grid-cols-[0.95fr_1.05fr]">
                    <div>
                      <p className="text-xs text-hive-muted">What happened</p>
                      <p className="mt-1 leading-6 text-hive-text">{event.action_summary}</p>
                    </div>
                    <div>
                      <p className="text-xs text-hive-muted">Output summary</p>
                      <p className="mt-1 leading-6 text-hive-text">{event.output_summary}</p>
                    </div>
                  </div>
                </div>
              </div>
            ))}
      </div>
    </section>
  );
}
