"use client";

import { useEffect, useMemo, useState } from "react";
import { AgentWorkspace } from "@/components/AgentWorkspace";
import { ChatCommandPanel } from "@/components/ChatCommandPanel";
import { MemoryPanel } from "@/components/MemoryPanel";
import { MetricsPanel } from "@/components/MetricsPanel";
import { Navbar } from "@/components/Navbar";
import { OutputPanel } from "@/components/OutputPanel";
import { RunTimeline } from "@/components/RunTimeline";
import { TaskGraph } from "@/components/TaskGraph";
import { AgentInfo, MemorySummary, RunRecord, getAgents, getMemorySummary, startRun } from "@/lib/api";

const fallbackAgents: AgentInfo[] = [
  "CEO Agent",
  "Model Selector Agent",
  "Research Agent",
  "Coding Agent",
  "Content Agent",
  "QA Agent"
].map((name) => ({
  name,
  role: "Waiting for backend metadata",
  assigned_model: "mock",
  status: "idle",
  latest_action: "Ready for command",
  completed_work: []
}));

export default function Home() {
  const [run, setRun] = useState<RunRecord>();
  const [agents, setAgents] = useState<AgentInfo[]>(fallbackAgents);
  const [memory, setMemory] = useState<MemorySummary>();
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string>();

  useEffect(() => {
    Promise.all([getAgents(), getMemorySummary()])
      .then(([agentData, memoryData]) => {
        setAgents(agentData);
        setMemory(memoryData);
      })
      .catch(() => {
        setError("Backend is not reachable yet. Start FastAPI on port 8000, then refresh.");
      });
  }, []);

  async function handleRun(command: string) {
    setIsRunning(true);
    setError(undefined);
    try {
      const result = await startRun(command);
      setRun(result);
      setAgents(result.agents);
      setMemory(result.memory);
    } catch {
      setError("Run failed. Confirm the backend is running at http://127.0.0.1:8000.");
    } finally {
      setIsRunning(false);
    }
  }

  const ceoModel = useMemo(() => run?.agents.find((agent) => agent.name === "CEO Agent")?.assigned_model ?? "gpt-5.5", [run]);
  const workerModel = useMemo(() => run?.agents.find((agent) => agent.name === "Coding Agent")?.assigned_model ?? "gpt-5.4-nano", [run]);

  return (
    <>
      <Navbar ceoModel={ceoModel} workerModel={workerModel} />
      <main className="mx-auto grid max-w-7xl gap-5 px-5 py-6">
        {error ? (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-100">{error}</div>
        ) : null}
        <div className="grid gap-5 xl:grid-cols-[1.05fr_0.95fr]">
          <ChatCommandPanel onRun={handleRun} isRunning={isRunning} submittedCommand={run?.command} />
          <MetricsPanel run={run} />
        </div>
        <TaskGraph graph={run?.task_graph} />
        <div className="grid gap-5 xl:grid-cols-[0.95fr_1.05fr]">
          <RunTimeline events={run?.events ?? []} />
          <MemoryPanel memory={memory} />
        </div>
        <AgentWorkspace agents={agents} />
        <OutputPanel run={run} />
      </main>
    </>
  );
}

