import MarkdownView from "../MarkdownView";
import { RunResult } from "../../types";

interface Props {
  run: RunResult;
}

export default function RunFinalReportPanel({ run }: Props) {
  const work = run.final_output.what_was_done.map((item) => `- ${item}`).join("\n") || "- No work summary available.";
  const artifacts = run.final_output.generated_artifacts.map((item) => `- ${item}`).join("\n") || "- No generated artifact list available.";
  const next = run.final_output.recommended_next_actions.map((item) => `- ${item}`).join("\n") || "- No next actions available.";
  const content = `### Final Summary
${run.final_output.summary || "No final summary was returned."}

#### Decisions / Work Completed
${work}

#### Generated Outputs
${artifacts}

#### Warnings / Next Steps
${next}`;
  return (
    <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4">
      <h3 className="text-xs font-bold text-[#909296] uppercase tracking-wider font-mono mb-3">Final Report</h3>
      <div className="bg-[#141517] border border-[#2c2e33] rounded p-4">
        <MarkdownView content={content} />
      </div>
    </section>
  );
}
