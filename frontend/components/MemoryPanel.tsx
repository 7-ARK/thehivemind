import { Brain } from "lucide-react";
import type { MemorySummary } from "@/lib/api";

type MemoryPanelProps = {
  memory?: MemorySummary;
};

export function MemoryPanel({ memory }: MemoryPanelProps) {
  const snippetCount = memory?.retrieved_snippets.length ?? 0;

  return (
    <section id="memory" className="panel p-5">
      <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-hive-amber" />
            <p className="fine-label">Memory</p>
          </div>
          <h2 className="mt-1 text-lg font-semibold text-hive-text">Relevant context, not everything</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-hive-muted">
            Agents do not read all memory. They retrieve only relevant context for the active command.
          </p>
        </div>
        <span className="rounded-full border border-hive-border bg-hive-panelSoft px-3 py-1 text-xs text-hive-muted">
          {snippetCount} chunks retrieved
        </span>
      </div>
      <div className="space-y-3">
        <div className="surface p-4">
          <div className="fine-label">Core memory</div>
          <p className="mt-2 text-sm leading-6 text-hive-text">{memory?.core_memory ?? "Core identity and operating principles will appear here."}</p>
        </div>
        <div className="surface p-4">
          <div className="fine-label">Current state</div>
          <p className="mt-2 text-sm leading-6 text-hive-text">{memory?.current_state ?? "No active project state yet."}</p>
        </div>
        <div className="surface p-4">
          <div className="fine-label">Retrieved snippets</div>
          <div className="mt-3 space-y-2">
            {(memory?.retrieved_snippets ?? []).length > 0 ? (
              memory?.retrieved_snippets.map((snippet) => (
                <div key={snippet.title} className="rounded-lg border border-hive-border bg-hive-shell p-3">
                  <div className="flex justify-between gap-3 text-xs">
                    <span className="font-medium text-hive-text">{snippet.title}</span>
                    <span className="text-hive-amber">score {snippet.relevance_score.toFixed(2)}</span>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-hive-muted">{snippet.content}</p>
                </div>
              ))
            ) : (
              <p className="text-sm leading-6 text-hive-muted">Run a command to retrieve local memory chunks.</p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
