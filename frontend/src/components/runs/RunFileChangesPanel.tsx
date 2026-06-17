import { FileSummaryItem } from "../../lib/runSummary";
import { ProjectChange } from "../../types";

interface Props {
  changes: ProjectChange[];
  created: FileSummaryItem[];
  updated: FileSummaryItem[];
}

export default function RunFileChangesPanel({ changes, created, updated }: Props) {
  const fallbackItems = [
    ...created,
    ...updated,
  ];
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4">
      <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono mb-3">File Changes</h3>
      {changes.length === 0 && fallbackItems.length === 0 ? (
        <p className="text-xs text-[#909296]">No file changes were recorded for this run.</p>
      ) : changes.length > 0 ? (
        <div className="space-y-2 max-h-96 overflow-auto">
          {changes.map((change, index) => (
            <div key={`${change.path}-${index}`} className="bg-[#141517] border border-[#2c2e33] rounded p-3 text-xs">
              <div className="flex items-start justify-between gap-3">
                <span className="font-mono text-[#e9ecef] break-all">{change.path}</span>
                <span className="text-[10px] text-[#20c997] uppercase font-mono">{change.operation}</span>
              </div>
              {change.before_summary && <p className="text-[11px] text-[#909296] mt-2">Before: {change.before_summary}</p>}
              <p className="text-[11px] text-[#909296] mt-2">After: {change.after_summary}</p>
              <div className="text-[10px] text-[#909296] font-mono mt-2">{change.agent_name} / {change.timestamp}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {fallbackItems.map((item) => (
            <div key={`${item.operation}-${item.path}`} className="bg-[#141517] border border-[#2c2e33] rounded p-2 text-xs flex justify-between gap-3">
              <span className="font-mono text-[#e9ecef] break-all">{item.path}</span>
              <span className="text-[10px] text-[#20c997] uppercase font-mono">{item.operation}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
