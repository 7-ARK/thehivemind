import type { AgentInfo } from "@/lib/api";
import { AgentCard } from "./AgentCard";

type AgentWorkspaceProps = {
  agents: AgentInfo[];
};

export function AgentWorkspace({ agents }: AgentWorkspaceProps) {
  return (
    <section className="panel rounded-lg p-5">
      <div className="mb-4">
        <h2 className="text-base font-semibold">Agent Workspace</h2>
        <p className="mt-1 text-sm text-hive-muted">Each worker reports role, model, status, and completed work.</p>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {agents.map((agent) => (
          <AgentCard key={agent.name} agent={agent} />
        ))}
      </div>
    </section>
  );
}

