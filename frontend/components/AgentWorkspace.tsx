import type { AgentInfo, RunEvent } from "@/lib/api";
import { AgentCard } from "./AgentCard";

type AgentWorkspaceProps = {
  agents: AgentInfo[];
  events?: RunEvent[];
};

export function AgentWorkspace({ agents, events = [] }: AgentWorkspaceProps) {
  return (
    <section id="agents" className="panel p-5">
      <div className="mb-5 flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="fine-label">Agent Workspace</p>
          <h2 className="mt-1 text-lg font-semibold text-hive-text">Who did the work?</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-hive-muted">
            Each card shows role, routed model, current action, last output, tokens, and estimated cost.
          </p>
        </div>
        <span className="text-xs text-hive-muted">{agents.filter((agent) => agent.status === "completed").length} active/completed agents</span>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {agents.map((agent) => {
          const event = events.find((item) => item.agent_name === agent.name);
          const progress = agent.status === "completed" ? 100 : event ? 70 : 12;
          return <AgentCard key={agent.name} agent={agent} event={event} progress={progress} />;
        })}
      </div>
    </section>
  );
}
