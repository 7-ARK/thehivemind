interface Props {
  path?: string;
  content?: string;
  loading?: boolean;
  error?: string | null;
}

export default function ProjectFilePreview({ path, content, loading, error }: Props) {
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4 h-full">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono">Preview</h3>
        {path && <span className="text-[10px] text-[#20c997] font-mono break-all">{path}</span>}
      </div>
      <div className="bg-[#141517] border border-[#2c2e33] rounded p-3 min-h-72 max-h-[34rem] overflow-auto">
        {loading && <p className="text-xs text-[#909296]">Loading file...</p>}
        {error && <p className="text-xs text-rose-300">{error}</p>}
        {!loading && !error && content && (
          <pre className="text-[11px] leading-relaxed text-[#e9ecef] whitespace-pre-wrap font-mono">{content}</pre>
        )}
        {!loading && !error && !content && <p className="text-xs text-[#909296]">Select a safe text file to preview.</p>}
      </div>
    </section>
  );
}
