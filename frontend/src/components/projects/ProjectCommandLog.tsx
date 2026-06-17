import { CommandResult } from "../../types";

interface Props {
  commands: CommandResult[];
}

export default function ProjectCommandLog({ commands }: Props) {
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4">
      <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono mb-3">Command Logs</h3>
      {commands.length === 0 ? (
        <p className="text-xs text-[#909296]">No safe commands recorded for the selected run.</p>
      ) : (
        <div className="space-y-2">
          {commands.map((command, index) => (
            <div key={index} className="bg-[#141517] border border-[#2c2e33] rounded p-3 text-xs">
              <div className="flex items-center justify-between gap-3">
                <code className="text-[#e9ecef] break-all">{command.command.join(" ")}</code>
                <span className={command.exit_code === 0 ? "text-[#20c997]" : "text-[#fab005]"}>exit {command.exit_code}</span>
              </div>
              {command.stderr && <pre className="text-[11px] text-rose-300 mt-2 whitespace-pre-wrap">{command.stderr}</pre>}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
