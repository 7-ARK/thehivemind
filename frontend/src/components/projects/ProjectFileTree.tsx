import { FileText } from "lucide-react";
import { ProjectFile } from "../../types";

interface Props {
  files: ProjectFile[];
  selectedPath?: string;
  onSelect: (path: string) => void;
}

export default function ProjectFileTree({ files, selectedPath, onSelect }: Props) {
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4 h-full">
      <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono mb-3">Files</h3>
      {files.length === 0 ? (
        <p className="text-xs text-[#909296]">No files created yet.</p>
      ) : (
        <div className="space-y-1 max-h-[30rem] overflow-auto">
          {files.map((file) => (
            <button
              key={file.path}
              onClick={() => onSelect(file.path)}
              className={`w-full text-left px-2 py-2 rounded border text-xs flex items-start gap-2 transition-colors ${
                selectedPath === file.path
                  ? "bg-[#20c997]/10 border-[#20c997]/30 text-[#e9ecef]"
                  : "bg-[#141517] border-[#2c2e33] text-[#909296] hover:text-[#e9ecef]"
              }`}
            >
              <FileText className="w-3.5 h-3.5 mt-0.5 text-[#20c997] shrink-0" />
              <span className="font-mono break-all">{file.path}</span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
