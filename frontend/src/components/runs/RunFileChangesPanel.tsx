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
  const userChanges = changes.filter((change) => !isSystemMetadataPath(change.path));
  const metadataChanges = changes.filter((change) => isSystemMetadataPath(change.path));
  const userFallbackItems = fallbackItems.filter((item) => !isSystemMetadataPath(item.path));
  const metadataFallbackItems = fallbackItems.filter((item) => isSystemMetadataPath(item.path));
  const hasChanges = changes.length > 0;
  const hasAnyFiles = changes.length > 0 || fallbackItems.length > 0;

  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono">User File Changes</h3>
        {hasAnyFiles && (
          <span className="text-[10px] font-mono text-[#909296]">
            user {hasChanges ? userChanges.length : userFallbackItems.length} / metadata {hasChanges ? metadataChanges.length : metadataFallbackItems.length}
          </span>
        )}
      </div>
      {!hasAnyFiles ? (
        <p className="text-xs text-[#909296]">No file changes were recorded for this run.</p>
      ) : hasChanges ? (
        <div className="space-y-2 max-h-96 overflow-auto">
          {userChanges.length === 0 && <p className="text-xs text-[#909296]">No user-facing file changes were recorded for this run.</p>}
          {userChanges.map((change, index) => (
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
          {userFallbackItems.length === 0 && <p className="text-xs text-[#909296]">No user-facing file changes were recorded for this run.</p>}
          {userFallbackItems.map((item) => (
            <div key={`${item.operation}-${item.path}`} className="bg-[#141517] border border-[#2c2e33] rounded p-2 text-xs flex justify-between gap-3">
              <span className="font-mono text-[#e9ecef] break-all">{item.path}</span>
              <span className="text-[10px] text-[#20c997] uppercase font-mono">{item.operation}</span>
            </div>
          ))}
        </div>
      )}
      {(metadataChanges.length > 0 || metadataFallbackItems.length > 0) && (
        <div className="mt-4 border-t border-[#2c2e33] pt-3">
          <h4 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono mb-2">System Metadata</h4>
          <div className="space-y-2 max-h-40 overflow-auto">
            {hasChanges
              ? metadataChanges.map((change, index) => (
                  <div key={`${change.path}-metadata-${index}`} className="bg-[#141517] border border-[#2c2e33] rounded p-2 text-xs flex justify-between gap-3">
                    <span className="font-mono text-[#e9ecef] break-all">{change.path}</span>
                    <span className="text-[10px] text-[#909296] uppercase font-mono">{change.operation}</span>
                  </div>
                ))
              : metadataFallbackItems.map((item) => (
                  <div key={`${item.operation}-${item.path}-metadata`} className="bg-[#141517] border border-[#2c2e33] rounded p-2 text-xs flex justify-between gap-3">
                    <span className="font-mono text-[#e9ecef] break-all">{item.path}</span>
                    <span className="text-[10px] text-[#909296] uppercase font-mono">{item.operation}</span>
                  </div>
                ))}
          </div>
        </div>
      )}
    </section>
  );
}

function isSystemMetadataPath(path: string): boolean {
  const normalized = path.replace(/\\/g, "/").toLowerCase();
  const name = normalized.split("/").pop() ?? normalized;
  return (
    name === "project_state.md" ||
    name === "manifest.json" ||
    name === "project_manifest.json" ||
    name === "memory_manifest.json" ||
    normalized.includes("/memory/") ||
    normalized.includes("memory_manifest") ||
    normalized.includes("context_packet") ||
    normalized.includes("run_summary.json") ||
    normalized.includes("timeline.json") ||
    normalized.includes("commands.json") ||
    normalized.includes("workspace_snapshot.json")
  );
}
