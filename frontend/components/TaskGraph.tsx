import { ArrowRight } from "lucide-react";
import type { TaskGraph as TaskGraphType } from "@/lib/api";

type TaskGraphProps = {
  graph?: TaskGraphType;
};

const fallbackNodes = ["Command", "CEO Plan", "Worker Tasks", "Agent Outputs", "QA Review", "Final Answer"];

export function TaskGraph({ graph }: TaskGraphProps) {
  const nodes = graph?.nodes.map((node) => node.label) ?? fallbackNodes;

  return (
    <section className="panel rounded-lg p-5">
      <h2 className="text-base font-semibold">Task Graph</h2>
      <div className="mt-4 flex flex-col gap-3 lg:flex-row lg:items-center">
        {nodes.map((node, index) => (
          <div key={node} className="flex items-center gap-3">
            <div className="min-w-36 rounded-md border border-hive-border bg-hive-panelSoft px-3 py-3 text-center text-sm">
              {node}
            </div>
            {index < nodes.length - 1 ? <ArrowRight className="hidden h-4 w-4 text-hive-muted lg:block" /> : null}
          </div>
        ))}
      </div>
    </section>
  );
}

