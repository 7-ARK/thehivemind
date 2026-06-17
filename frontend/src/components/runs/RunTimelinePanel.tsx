import { RunEvent } from "../../types";

interface Props {
  events: RunEvent[];
  mode: "mock" | "live";
}

export default function RunTimelinePanel({ events, mode }: Props) {
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4">
      <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono mb-3">Timeline</h3>
      {events.length === 0 ? (
        <p className="text-xs text-[#909296]">No timeline events were recorded for this run.</p>
      ) : (
        <div className="space-y-3">
          {events.map((event, index) => (
            <div key={`${event.agent_name}-${event.timestamp}-${index}`} className="bg-[#141517] border border-[#2c2e33] rounded p-3">
              <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-2">
                <div>
                  <div className="text-[10px] text-[#20c997] font-mono uppercase">Step {index + 1}</div>
                  <h4 className="text-xs font-bold text-[#e9ecef]">{event.agent_name}</h4>
                  <p className="text-[11px] text-[#909296] mt-1">{event.agent_role}</p>
                </div>
                <div className="flex flex-wrap gap-2 text-[10px] font-mono text-[#909296]">
                  <span>{event.status}</span>
                  {mode === "mock" ? (
                    <>
                      <span>Actual provider: mock</span>
                      <span>Planned model: {event.model_used}</span>
                      <span className="text-[#fab005]">sim ${event.estimated_cost_usd.toFixed(6)}</span>
                    </>
                  ) : (
                    <>
                      <span>{event.provider ?? "provider n/a"}</span>
                      <span>{event.model_used}</span>
                      <span className="text-[#fab005]">${event.estimated_cost_usd.toFixed(6)}</span>
                    </>
                  )}
                </div>
              </div>
              <p className="text-xs text-[#e9ecef] mt-3">{event.action_summary}</p>
              {event.input_summary && <p className="text-[11px] text-[#909296] mt-2">Input: {truncate(event.input_summary, 260)}</p>}
              {event.output_summary && <p className="text-[11px] text-[#909296] mt-2">Output: {truncate(event.output_summary, 360)}</p>}
              <div className="flex flex-wrap gap-3 text-[10px] text-[#909296] font-mono mt-3">
                <span>{event.estimated_input_tokens.toLocaleString()} in</span>
                <span>{event.estimated_output_tokens.toLocaleString()} out</span>
                {event.artifact_id && <span className="text-[#20c997]">artifact {event.artifact_id}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function truncate(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max)}...` : value;
}
