import { ProjectRunEntry } from "../../types";

interface Props {
  runs: ProjectRunEntry[];
  selectedRunId?: string;
  onSelect: (runId: string) => void;
  onOpenRunDetail?: (runId: string) => void;
}

export default function ProjectRunHistory({ runs, selectedRunId, onSelect, onOpenRunDetail }: Props) {
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4">
      <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono mb-3">Run History</h3>
      {runs.length === 0 ? (
        <p className="text-xs text-[#909296]">No runs recorded for this project.</p>
      ) : (
        <div className="space-y-2">
          {runs.map((run) => (
            <div
              key={run.run_id}
              className={`flex items-start gap-2 p-3 rounded border text-xs ${
                selectedRunId === run.run_id ? "border-[#20c997]/40 bg-[#20c997]/10" : "border-[#2c2e33] bg-[#141517]"
              }`}
            >
              <button onClick={() => onSelect(run.run_id)} className="min-w-0 flex-1 text-left">
                <div className="font-mono text-[#e9ecef] break-all">{run.run_id}</div>
                <div className="text-[#909296] mt-1">{run.summary}</div>
              </button>
              {onOpenRunDetail && (
                <button
                  onClick={() => onOpenRunDetail(run.run_id)}
                  className="shrink-0 bg-[#25262b] hover:bg-[#2c2e33] border border-[#2c2e33] text-[#20c997] px-2.5 py-1.5 rounded text-[10px] font-bold"
                >
                  View
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
