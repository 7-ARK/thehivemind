import MarkdownView from "../MarkdownView";
import { ProjectFile } from "../../types";

interface Props {
  content: string;
  loading?: boolean;
  files?: ProjectFile[];
}

export default function ProjectStateCard({ content, loading, files = [] }: Props) {
  const displayContent = normalizeProjectState(content, files);

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
        ) : displayContent ? (
          <MarkdownView content={displayContent} />
        ) : (
          <p className="text-xs text-[#909296]">No project workspace yet.</p>
        )}
      </div>
    </section>
  );
}

function normalizeProjectState(content: string, files: ProjectFile[]): string {
  if (!content) return "";
  let next = content
    .replace("## What Has Been Built\nCreated files:", "## Changes In Last Run\nCreated in this run:")
    .replace("Updated files:", "Updated in this run:");
  if (!next.includes("## Current Project Files") && files.length > 0) {
    const fileList = files.map((file) => `- ${file.path}`).join("\n");
    next = `${next.trim()}\n\n## Current Project Files\n${fileList}\n`;
  }
  return next;
}
