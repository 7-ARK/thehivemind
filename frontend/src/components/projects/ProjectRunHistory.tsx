import { ProjectRunEntry } from "../../types";

interface Props {
  runs: ProjectRunEntry[];
  selectedRunId?: string;
  onSelect: (runId: string) => void;
}

export default function ProjectRunHistory({ runs, selectedRunId, onSelect }: Props) {
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4">
      <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono mb-3">Run History</h3>
      {runs.length === 0 ? (
        <p className="text-xs text-[#909296]">No runs recorded for this project.</p>
      ) : (
        <div className="space-y-2">
          {runs.map((run) => (
            <button
              key={run.run_id}
              onClick={() => onSelect(run.run_id)}
              className={`w-full text-left p-3 rounded border text-xs ${
                selectedRunId === run.run_id ? "border-[#20c997]/40 bg-[#20c997]/10" : "border-[#2c2e33] bg-[#141517]"
              }`}
            >
              <div className="font-mono text-[#e9ecef]">{run.run_id}</div>
              <div className="text-[#909296] mt-1">{run.summary}</div>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
