import { Bot, Check, Circle } from "lucide-react";
import type { AgentInfo, RunEvent } from "@/lib/api";

type AgentCardProps = {
  agent: AgentInfo;
  event?: RunEvent;
  progress: number;
};

export function AgentCard({ agent, event, progress }: AgentCardProps) {
  const active = agent.status === "completed";
  const tokens = event ? event.estimated_input_tokens + event.estimated_output_tokens : 0;

  return (
    <article className="metric-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-hive-border bg-hive-shell">
            {active ? <Check className="h-4 w-4 text-hive-green" /> : <Bot className="h-4 w-4 text-hive-muted" />}
          </div>
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-hive-text">{agent.name}</h3>
            <p className="mt-1 text-xs leading-5 text-hive-muted">{agent.role}</p>
          </div>
        </div>
        <span className={active ? "rounded-full bg-hive-green/12 px-2 py-1 text-[11px] text-hive-green" : "rounded-full bg-hive-shell px-2 py-1 text-[11px] text-hive-muted"}>
          {agent.status}
        </span>
      </div>
      <div className="mt-4 grid gap-2 rounded-lg border border-hive-border bg-hive-panel p-3 text-xs">
        <div className="flex justify-between gap-3">
          <span className="text-hive-muted">Model</span>
          <span className="text-right text-hive-text">{event?.model_used ?? agent.assigned_model}</span>
        </div>
        <div className="flex justify-between gap-3">
          <span className="text-hive-muted">Tokens / cost</span>
          <span className="text-right text-hive-text">
            {tokens.toLocaleString()} / ${(event?.estimated_cost_usd ?? 0).toFixed(6)}
          </span>
        </div>
      </div>
      <div className="mt-4">
        <div className="flex items-center justify-between text-xs">
          <span className="text-hive-muted">Progress</span>
          <span className="text-hive-text">{progress}%</span>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-hive-shell">
          <div className="h-full rounded-full bg-hive-cyan" style={{ width: `${progress}%` }} />
        </div>
      </div>
      <div className="mt-4 flex gap-2">
        <Circle className="mt-1 h-2.5 w-2.5 fill-hive-amber text-hive-amber" />
        <div>
          <p className="text-xs text-hive-muted">Current action</p>
          <p className="mt-1 text-sm leading-6 text-hive-text">{agent.latest_action}</p>
        </div>
      </div>
      {event ? (
        <div className="mt-4 rounded-lg border border-hive-border bg-hive-panel p-3">
          <p className="text-xs text-hive-muted">Last output summary</p>
          <p className="mt-1 text-sm leading-6 text-hive-text">{event.output_summary}</p>
        </div>
      ) : null}
      {agent.completed_work.length > 0 ? (
        <ul className="mt-3 space-y-2 text-xs text-hive-muted">
          {agent.completed_work.map((item) => (
            <li key={item} className="rounded-lg border border-hive-border bg-hive-shell p-2.5 leading-5">
              {item}
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}
