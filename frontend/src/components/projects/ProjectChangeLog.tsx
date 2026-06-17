import { ProjectChange } from "../../types";

interface Props {
  changes: ProjectChange[];
}

export default function ProjectChangeLog({ changes }: Props) {
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4">
      <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono mb-3">File Changes</h3>
      {changes.length === 0 ? (
        <p className="text-xs text-[#909296]">No file changes logged yet.</p>
      ) : (
        <div className="space-y-2 max-h-72 overflow-auto">
          {changes.slice().reverse().map((change, index) => (
            <div key={`${change.run_id}-${change.path}-${index}`} className="bg-[#141517] border border-[#2c2e33] rounded p-3 text-xs">
              <div className="flex items-center justify-between gap-3">
                <span className="font-mono text-[#e9ecef] break-all">{change.path}</span>
                <span className="text-[10px] text-[#20c997] uppercase font-mono">{change.operation}</span>
              </div>
              <p className="text-[#909296] mt-1">{change.after_summary}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
