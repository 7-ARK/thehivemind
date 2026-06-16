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
    <section className="panel rounded-lg p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Command Center</h2>
          <p className="mt-1 text-sm text-hive-muted">Send one instruction and watch the agents divide the work.</p>
        </div>
        <span className="rounded-md border border-hive-border bg-hive-panelSoft px-2.5 py-1 text-xs text-hive-muted">
          local mock
        </span>
      </div>
      <form onSubmit={handleSubmit} className="space-y-3">
        <textarea
          value={command}
          onChange={(event) => setCommand(event.target.value)}
          placeholder="Tell TheHiveMind what to build, research, automate, or plan..."
          className="min-h-32 w-full resize-y rounded-md border border-hive-border bg-hive-bg px-4 py-3 text-sm text-hive-text outline-none transition focus:border-hive-accent"
        />
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-hive-muted">
            Hidden chain-of-thought stays hidden; practical work logs are shown.
          </p>
          <button
            type="submit"
            disabled={isRunning}
            className="inline-flex items-center justify-center gap-2 rounded-md bg-hive-accent px-4 py-2 text-sm font-semibold text-hive-bg transition hover:bg-[#ffd36b] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Run Hive
          </button>
        </div>
      </form>
      {submittedCommand ? (
        <div className="mt-4 rounded-md border border-hive-border bg-hive-panelSoft p-3">
          <div className="text-xs uppercase text-hive-muted">Last command</div>
          <p className="mt-1 text-sm">{submittedCommand}</p>
        </div>
      ) : null}
    </section>
  );
}

