"use client";

import { useEffect, useMemo, useState } from "react";
import { AgentWorkspace } from "@/components/AgentWorkspace";
import { ChatCommandPanel } from "@/components/ChatCommandPanel";
import { MemoryPanel } from "@/components/MemoryPanel";
import { MetricsPanel } from "@/components/MetricsPanel";
import { Navbar } from "@/components/Navbar";
import { OutputPanel } from "@/components/OutputPanel";
import { RunTimeline } from "@/components/RunTimeline";
import { Sidebar } from "@/components/Sidebar";
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
  const [backendOnline, setBackendOnline] = useState(true);

  useEffect(() => {
    Promise.all([getAgents(), getMemorySummary()])
      .then(([agentData, memoryData]) => {
        setAgents(agentData);
        setMemory(memoryData);
        setBackendOnline(true);
      })
      .catch(() => {
        setBackendOnline(false);
        setError("Backend offline. Start FastAPI to run live mock orchestration.");
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
      setBackendOnline(true);
    } catch {
      setBackendOnline(false);
      setError("Backend offline. Start FastAPI to run live mock orchestration.");
    } finally {
      setIsRunning(false);
    }
  }

  const ceoModel = useMemo(() => run?.agents.find((agent) => agent.name === "CEO Agent")?.assigned_model ?? "gpt-5.5", [run]);
  const workerModel = useMemo(() => run?.agents.find((agent) => agent.name === "Coding Agent")?.assigned_model ?? "gpt-5.4-nano", [run]);
  const runTitle = run?.command ?? "New orchestration run";

  return (
    <div className="min-h-screen bg-hive-bg">
      <Sidebar backendOnline={backendOnline} />
      <div className="lg:pl-64">
        <Navbar ceoModel={ceoModel} workerModel={workerModel} backendOnline={backendOnline} runTitle={runTitle} />
        <main className="grid gap-5 px-4 py-5 sm:px-5 lg:px-8">
          {error ? (
            <div className="rounded-xl border border-hive-warning/45 bg-hive-warning/10 px-4 py-3 text-sm text-[#f0d7b8]">
              <div className="font-medium">Backend offline</div>
              <p className="mt-1 text-xs leading-5 text-hive-muted">
                {error} Expected backend URL: <span className="text-hive-text">http://127.0.0.1:8000</span>
              </p>
            </div>
          ) : null}
          <div className="grid gap-5 2xl:grid-cols-[0.95fr_1.05fr]">
            <ChatCommandPanel onRun={handleRun} isRunning={isRunning} submittedCommand={run?.command} />
            <MetricsPanel run={run} />
          </div>
          <TaskGraph graph={run?.task_graph} />
          <AgentWorkspace agents={agents} events={run?.events ?? []} />
          <div className="grid gap-5 xl:grid-cols-[1.08fr_0.92fr]">
            <RunTimeline events={run?.events ?? []} />
            <MemoryPanel memory={memory} />
          </div>
          <OutputPanel run={run} />
          <section id="settings" className="panel p-5">
            <p className="fine-label">Settings</p>
            <p className="mt-2 text-sm leading-6 text-hive-muted">
              Live providers are intentionally disabled for this pass. Mock mode keeps the dashboard safe for local demos.
            </p>
          </section>
        </main>
      </div>
    </div>
  );
}
