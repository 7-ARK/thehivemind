import { ArtifactRecord } from "../../types";

interface Props {
  artifacts: ArtifactRecord[];
}

export default function ProjectArtifactList({ artifacts }: Props) {
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4">
      <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono mb-3">Artifacts</h3>
      {artifacts.length === 0 ? (
        <p className="text-xs text-[#909296]">No artifacts recorded for the selected run.</p>
      ) : (
        <div className="space-y-2 max-h-72 overflow-auto">
          {artifacts.map((artifact) => (
            <div key={artifact.id} className="bg-[#141517] border border-[#2c2e33] rounded p-3 text-xs">
              <div className="flex items-center justify-between gap-3">
                <span className="font-mono text-[#e9ecef] break-all">{artifact.name}</span>
                <span className="text-[10px] text-[#20c997] uppercase font-mono">{artifact.type}</span>
              </div>
              <p className="text-[#909296] mt-1">{artifact.summary}</p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
