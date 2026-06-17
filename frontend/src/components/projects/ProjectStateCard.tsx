import MarkdownView from "../MarkdownView";

interface Props {
  content: string;
  loading?: boolean;
}

export default function ProjectStateCard({ content, loading }: Props) {
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono">Project State</h3>
        <span className="text-[10px] text-[#20c997] bg-[#20c997]/10 border border-[#20c997]/20 px-2 py-0.5 rounded font-mono">
          project_state.md
        </span>
      </div>
      <div className="bg-[#141517] border border-[#2c2e33] rounded p-3 max-h-80 overflow-auto">
        {loading ? (
          <p className="text-xs text-[#909296]">Loading project state...</p>
        ) : content ? (
          <MarkdownView content={content} />
        ) : (
          <p className="text-xs text-[#909296]">No project workspace yet.</p>
        )}
      </div>
    </section>
  );
}
