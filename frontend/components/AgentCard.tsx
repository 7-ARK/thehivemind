import { Bot, Check } from "lucide-react";
import type { AgentInfo } from "@/lib/api";

type AgentCardProps = {
  agent: AgentInfo;
};

export function AgentCard({ agent }: AgentCardProps) {
  const active = agent.status === "completed";

  return (
    <article className="rounded-lg border border-hive-border bg-hive-panelSoft p-4">
      <div className="flex items-start gap-3">
        <div className="grid h-9 w-9 place-items-center rounded-md border border-hive-border bg-hive-bg">
          {active ? <Check className="h-4 w-4 text-hive-teal" /> : <Bot className="h-4 w-4 text-hive-muted" />}
        </div>
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold">{agent.name}</h3>
          <p className="text-xs text-hive-muted">{agent.role}</p>
        </div>
      </div>
      <div className="mt-4 grid gap-2 text-xs">
        <div className="flex justify-between gap-3">
          <span className="text-hive-muted">Model</span>
          <span className="text-right text-hive-text">{agent.assigned_model}</span>
        </div>
        <div className="flex justify-between gap-3">
          <span className="text-hive-muted">Status</span>
          <span className={active ? "text-hive-teal" : "text-hive-muted"}>{agent.status}</span>
        </div>
      </div>
      <p className="mt-4 text-sm text-hive-text">{agent.latest_action}</p>
      {agent.completed_work.length > 0 ? (
        <ul className="mt-3 space-y-2 text-xs text-hive-muted">
          {agent.completed_work.map((item) => (
            <li key={item} className="rounded border border-hive-border bg-hive-bg p-2">
              {item}
            </li>
          ))}
        </ul>
      ) : null}
    </article>
  );
}

