import { ProjectManifestFile } from "../../types";

interface Props {
  files: ProjectManifestFile[];
}

export default function ProjectManifestTable({ files }: Props) {
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4">
      <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono mb-3">Manifest</h3>
      {files.length === 0 ? (
        <p className="text-xs text-[#909296]">No files created yet.</p>
      ) : (
        <div className="overflow-auto">
          <table className="w-full text-xs">
            <thead className="text-[10px] uppercase text-[#909296] font-mono">
              <tr className="border-b border-[#2c2e33]">
                <th className="text-left py-2 pr-3">Path</th>
                <th className="text-left py-2 pr-3">Type</th>
                <th className="text-right py-2 pr-3">Size</th>
                <th className="text-left py-2">Summary</th>
              </tr>
            </thead>
            <tbody>
              {files.map((file) => (
                <tr key={file.path} className="border-b border-[#2c2e33]/70">
                  <td className="py-2 pr-3 font-mono text-[#e9ecef] whitespace-nowrap">{file.path}</td>
                  <td className="py-2 pr-3 text-[#20c997]">{file.file_type}</td>
                  <td className="py-2 pr-3 text-right text-[#909296]">{file.size_bytes.toLocaleString()}</td>
                  <td className="py-2 text-[#909296] min-w-64">{file.summary}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
