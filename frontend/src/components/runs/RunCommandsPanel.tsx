import { CommandResult } from "../../types";

interface Props {
  commands: CommandResult[];
}

export default function RunCommandsPanel({ commands }: Props) {
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4">
      <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono mb-3">Safe Commands</h3>
      {commands.length === 0 ? (
        <p className="text-xs text-[#909296]">No command logs were recorded for this run.</p>
      ) : (
        <div className="space-y-2">
          {commands.map((command, index) => (
            <div key={index} className="bg-[#141517] border border-[#2c2e33] rounded p-3 text-xs">
              <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2">
                <code className="text-[#e9ecef] break-all">{command.command.join(" ")}</code>
                <span className={command.allowed && command.exit_code === 0 ? "text-[#20c997]" : "text-[#fab005]"}>
                  {command.allowed ? `exit ${command.exit_code}` : "blocked"}
                </span>
              </div>
              <div className="flex flex-wrap gap-3 text-[10px] text-[#909296] font-mono mt-2">
                <span>cwd: {command.cwd}</span>
                <span>{command.duration_ms}ms</span>
                {command.blocked_reason && <span className="text-[#fab005]">{command.blocked_reason}</span>}
              </div>
              {command.stdout && <pre className="text-[11px] text-[#909296] mt-2 whitespace-pre-wrap">{command.stdout.slice(0, 700)}</pre>}
              {command.stderr && <pre className="text-[11px] text-rose-300 mt-2 whitespace-pre-wrap">{command.stderr.slice(0, 700)}</pre>}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
