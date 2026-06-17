import { ArtifactRecord } from "../../types";

interface Props {
  artifacts: ArtifactRecord[];
}

export default function RunArtifactsPanel({ artifacts }: Props) {
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4">
      <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono mb-3">Artifacts</h3>
      {artifacts.length === 0 ? (
        <p className="text-xs text-[#909296]">No artifacts were recorded for this run.</p>
      ) : (
        <div className="space-y-2 max-h-96 overflow-auto">
          {artifacts.map((artifact) => (
            <div key={artifact.id} className="bg-[#141517] border border-[#2c2e33] rounded p-3 text-xs">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-mono text-[#e9ecef] break-all">{artifact.name}</div>
                  <div className="text-[10px] text-[#909296] mt-1">{artifact.agent_name}</div>
                </div>
                <span className="text-[10px] text-[#20c997] uppercase font-mono">{artifact.type}</span>
              </div>
              <p className="text-[#909296] mt-2">{artifact.summary}</p>
              <p className="text-[10px] text-[#909296] font-mono mt-2 break-all">{artifact.path}</p>
              <p className="text-[10px] text-[#909296] font-mono mt-2">{artifact.created_at}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
