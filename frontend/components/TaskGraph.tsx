import { ArrowRight } from "lucide-react";
import type { TaskGraph as TaskGraphType } from "@/lib/api";

type TaskGraphProps = {
  graph?: TaskGraphType;
};

const fallbackNodes = ["Command", "CEO Plan", "Worker Tasks", "Agent Outputs", "QA Review", "Final Answer"];

export function TaskGraph({ graph }: TaskGraphProps) {
  const nodes = graph?.nodes ?? fallbackNodes.map((label) => ({ id: label, label, status: "pending" }));

  return (
    <section className="panel p-5">
      <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="fine-label">Task Graph</p>
          <h2 className="mt-1 text-lg font-semibold text-hive-text">How the command moves through the system</h2>
        </div>
        <span className="text-xs text-hive-muted">simple execution flow</span>
      </div>
      <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        {nodes.map((node, index) => (
          <div key={node.id} className="relative">
            <div className="min-h-28 rounded-lg border border-hive-border bg-hive-panelSoft p-4">
              <div className="flex h-7 w-7 items-center justify-center rounded-full bg-hive-shell text-xs text-hive-muted">
                {index + 1}
              </div>
              <div className="mt-3 text-sm font-semibold text-hive-text">{node.label}</div>
              <div className={node.status === "completed" ? "mt-2 text-xs text-hive-green" : "mt-2 text-xs text-hive-muted"}>
                {node.status === "completed" ? "completed" : "pending run"}
              </div>
            </div>
            {index < nodes.length - 1 ? (
              <ArrowRight className="absolute -right-4 top-1/2 z-10 hidden h-5 w-5 -translate-y-1/2 text-hive-faint xl:block" />
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}
