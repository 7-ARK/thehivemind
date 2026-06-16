import { Brain } from "lucide-react";
import type { MemorySummary } from "@/lib/api";

type MemoryPanelProps = {
  memory?: MemorySummary;
};

export function MemoryPanel({ memory }: MemoryPanelProps) {
  return (
    <section className="panel rounded-lg p-5">
      <div className="mb-4 flex items-center gap-2">
        <Brain className="h-4 w-4 text-hive-accent" />
        <h2 className="text-base font-semibold">Memory</h2>
      </div>
      <div className="space-y-3">
        <div className="rounded-md border border-hive-border bg-hive-panelSoft p-3">
          <div className="text-xs uppercase text-hive-muted">Core memory</div>
          <p className="mt-1 text-sm">{memory?.core_memory ?? "Core identity and operating principles will appear here."}</p>
        </div>
        <div className="rounded-md border border-hive-border bg-hive-panelSoft p-3">
          <div className="text-xs uppercase text-hive-muted">Current state</div>
          <p className="mt-1 text-sm">{memory?.current_state ?? "No active project state yet."}</p>
        </div>
        <div className="rounded-md border border-hive-border bg-hive-panelSoft p-3">
          <div className="text-xs uppercase text-hive-muted">Retrieved snippets</div>
          <div className="mt-2 space-y-2">
            {(memory?.retrieved_snippets ?? []).length > 0 ? (
              memory?.retrieved_snippets.map((snippet) => (
                <div key={snippet.title} className="rounded border border-hive-border bg-hive-bg p-2">
                  <div className="flex justify-between gap-3 text-xs">
                    <span className="font-medium text-hive-text">{snippet.title}</span>
                    <span className="text-hive-accent">{snippet.relevance_score.toFixed(2)}</span>
                  </div>
                  <p className="mt-1 text-xs text-hive-muted">{snippet.content}</p>
                </div>
              ))
            ) : (
              <p className="text-sm text-hive-muted">Run a command to retrieve local memory chunks.</p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

