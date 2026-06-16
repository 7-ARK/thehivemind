"use client";

import { Loader2, Send } from "lucide-react";
import { FormEvent, useState } from "react";

type ChatCommandPanelProps = {
  onRun: (command: string) => Promise<void>;
  isRunning: boolean;
  submittedCommand?: string;
};

export function ChatCommandPanel({ onRun, isRunning, submittedCommand }: ChatCommandPanelProps) {
  const [command, setCommand] = useState("Build a launch plan for a Greek yogurt business");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!command.trim() || isRunning) return;
    await onRun(command.trim());
  }

  return (
    <section id="command" className="panel p-5 md:p-6">
      <div className="mb-5 flex items-start justify-between gap-3">
        <div>
          <p className="fine-label">Command Center</p>
          <h2 className="mt-1 text-lg font-semibold text-hive-text">What should the hive work on?</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-hive-muted">
            TheHiveMind will plan the work, assign agents, track steps, and summarize results.
          </p>
        </div>
        <span className="rounded-full border border-hive-border bg-hive-panelSoft px-3 py-1 text-xs text-hive-muted">
          local mock
        </span>
      </div>
      <form onSubmit={handleSubmit} className="space-y-3">
        <textarea
          value={command}
          onChange={(event) => setCommand(event.target.value)}
          placeholder="Tell TheHiveMind what to plan, build, research, or automate..."
          className="min-h-36 w-full resize-y rounded-lg border border-hive-border bg-hive-shell px-4 py-4 text-sm leading-6 text-hive-text outline-none transition placeholder:text-hive-faint focus:border-hive-amber focus:ring-2 focus:ring-hive-amber/10"
        />
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs leading-5 text-hive-muted">
            Practical work logs are shown: assignments, model choices, memory retrieval, cost, and output.
          </p>
          <button
            type="submit"
            disabled={isRunning}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-hive-amber px-4 py-2.5 text-sm font-semibold text-hive-bg transition hover:bg-[#e1b363] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Run Hive
          </button>
        </div>
      </form>
      {submittedCommand ? (
        <div className="mt-5 rounded-lg border border-hive-border bg-hive-panelSoft p-4">
          <div className="fine-label">Submitted command</div>
          <p className="mt-2 text-sm leading-6 text-hive-text">{submittedCommand}</p>
        </div>
      ) : null}
    </section>
  );
}
