import React, { useState, useEffect } from "react";
import UsageDashboard from "./components/usage/UsageDashboard";
import Orchestrator from "./components/Orchestrator";
import ProjectWorkspacePanel from "./components/projects/ProjectWorkspacePanel";
import { getHealth, getProviderStatus } from "./lib/api";
import {
  LayoutDashboard,
  PlayCircle,
  BarChart3,
  Brain,
  Cpu,
  Layers,
  Settings,
  Terminal,
  Database,
  Sparkles,
  Award,
  Zap,
  CheckCircle,
  Fingerprint,
  Info
} from "lucide-react";

export default function App() {
  const [activeTab, setActiveTab] = useState<"orchestrator" | "projects" | "reports" | "agents" | "memory">("orchestrator");
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [backendStatus, setBackendStatus] = useState<"online" | "offline">("online");
  const [mockMode, setMockMode] = useState(true);
  const [liveCallsAllowed, setLiveCallsAllowed] = useState(false);
  const [ceoModel, setCeoModel] = useState("gpt-5.5");
  const [workerModel, setWorkerModel] = useState("gpt-5.4-nano");

  useEffect(() => {
    Promise.all([getHealth(), getProviderStatus()])
      .then(([health, providers]) => {
        setBackendStatus("online");
        setMockMode(health.mock_mode);
        setLiveCallsAllowed(providers.live_calls_allowed);
        setCeoModel(String(providers.default_models.ceo_model ?? "gpt-5.5"));
        setWorkerModel(String(providers.default_models.cheap_worker_model ?? "gpt-5.4-nano"));
      })
      .catch(() => {
        setBackendStatus("offline");
      });
  }, []);

  // When a workflow completes, increment state so the Usage dashboard re-fetches!
  const handleWorkflowCompleted = () => {
    setRefreshTrigger((prev) => prev + 1);
  };

  return (
    <div className="min-h-screen bg-[#141517] text-[#e9ecef] font-sans flex text-sm selection:bg-[#20c997]/20 antialiased selection:text-[#20c997]">
      
      {/* 1. SIDEBAR PANEL */}
      <aside className="w-64 bg-[#1a1b1e] border-r border-[#2c2e33] flex flex-col justify-between shrink-0 hidden md:flex">
        <div className="p-5">
          {/* Brand Logo */}
          <div className="flex items-center gap-2.5 px-1 pb-4 border-b border-[#2c2e33]">
            <div className="w-7 h-7 rounded-sm bg-[#20c997] flex items-center justify-center text-[#141517] font-bold text-sm tracking-tight select-none">
              Ω
            </div>
            <div>
              <div className="font-bold tracking-wider text-sm text-[#e9ecef] flex items-center gap-1 font-mono uppercase">
                TheHiveMind
                <span className="text-[9px] bg-[#2c2e33] text-[#20c997] font-mono border border-[#2c2e33] px-1 py-0.2 rounded font-bold">
                  OS
                </span>
              </div>
              <p className="text-[10px] text-[#909296] uppercase tracking-[1px] font-mono mt-0.5">Orchestration Cluster</p>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="mt-6 space-y-1.5">
            <button
              id="nav-btn-orchestrator"
              onClick={() => setActiveTab("orchestrator")}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-xs font-semibold tracking-wide cursor-pointer transition-colors ${
                activeTab === "orchestrator"
                  ? "bg-[#2c2e33] text-[#20c997] font-semibold border-l-2 border-[#20c997]"
                  : "text-[#909296] hover:bg-[#25262b] hover:text-[#e9ecef]"
              }`}
            >
              <PlayCircle className="w-4 h-4 shrink-0" />
              <span>Command Console</span>
            </button>

            <button
              id="nav-btn-projects"
              onClick={() => setActiveTab("projects")}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-xs font-semibold tracking-wide cursor-pointer transition-colors ${
                activeTab === "projects"
                  ? "bg-[#2c2e33] text-[#20c997] font-semibold border-l-2 border-[#20c997]"
                  : "text-[#909296] hover:bg-[#25262b] hover:text-[#e9ecef]"
              }`}
            >
              <Database className="w-4 h-4 shrink-0" />
              <span>Project Workspace</span>
            </button>

            <button
              id="nav-btn-reports"
              onClick={() => setActiveTab("reports")}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-xs font-semibold tracking-wide cursor-pointer transition-colors ${
                activeTab === "reports"
                  ? "bg-[#2c2e33] text-[#20c997] font-semibold border-l-2 border-[#20c997]"
                  : "text-[#909296] hover:bg-[#25262b] hover:text-[#e9ecef]"
              }`}
            >
              <BarChart3 className="w-4 h-4 shrink-0" />
              <span>Usage &amp; Costs</span>
            </button>

            <button
              id="nav-btn-agents"
              onClick={() => setActiveTab("agents")}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-xs font-semibold tracking-wide cursor-pointer transition-colors ${
                activeTab === "agents"
                  ? "bg-[#2c2e33] text-[#20c997] font-semibold border-l-2 border-[#20c997]"
                  : "text-[#909296] hover:bg-[#25262b] hover:text-[#e9ecef]"
              }`}
            >
              <Cpu className="w-4 h-4 shrink-0" />
              <span>Agents Registry</span>
            </button>

            <button
              id="nav-btn-memory"
              onClick={() => setActiveTab("memory")}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-xs font-semibold tracking-wide cursor-pointer transition-colors ${
                activeTab === "memory"
                  ? "bg-[#2c2e33] text-[#20c997] font-semibold border-l-2 border-[#20c997]"
                  : "text-[#909296] hover:bg-[#25262b] hover:text-[#e9ecef]"
              }`}
            >
              <Brain className="w-4 h-4 shrink-0" />
              <span>Retrieval / Memory</span>
            </button>
          </nav>
        </div>

        {/* Bottom Status Card */}
        <div className="p-4 border-t border-[#2c2e33]">
          <div className="bg-[#25262b] border border-[#2c2e33] p-3 rounded-lg space-y-2">
            <div className="flex items-center justify-between text-[11px] font-mono leading-none">
              <span className="text-[#909296] font-semibold text-[10px] uppercase">System Status</span>
              <span className={`inline-flex items-center gap-1.5 font-bold ${
                backendStatus === "online" ? "text-[#20c997]" : "text-rose-500"
              }`}>
                <span className={`w-2 h-2 rounded-full ${
                  backendStatus === "online" ? "bg-[#20c997]" : "bg-rose-500"
                }`} />
                {backendStatus.toUpperCase()}
              </span>
            </div>
            
            <div className="border-t border-[#2c2e33] my-2" />

            <div className="flex items-center justify-between text-[11px] font-mono leading-none">
              <span className="text-[#909296]">Mode Engine</span>
              <span className="text-[#fab005] font-semibold">
                {mockMode || !liveCallsAllowed ? "MOCK SAFE" : "LIVE READY"}
              </span>
            </div>
          </div>
        </div>
      </aside>

      {/* 2. MAIN HUB FIELD */}
      <div className="flex-1 flex flex-col min-w-0">
        
        {/* top Sticky Header */}
        <header className="h-16 border-b border-[#2c2e33] bg-[#1a1b1e]/90 backdrop-blur-sm px-6 flex items-center justify-between sticky top-0 z-40">
          <div className="flex items-center gap-3">
            {/* Mobile Title logo placeholder */}
            <div className="w-6 h-6 rounded bg-[#20c997] flex items-center justify-center md:hidden font-mono text-[#141517] text-xs font-bold animate-pulse">
              Ω
            </div>
            <h2 className="text-sm font-semibold text-[#e9ecef] font-mono tracking-wider hidden md:inline">
              ORCHESTRATION COMMAND MAINBOARD
            </h2>
          </div>

          {/* Top Model and status Badges */}
          <div className="flex items-center gap-3 text-xs">
            <div className="hidden lg:flex items-center gap-2">
              <span className="text-[10px] text-[#909296] font-mono tracking-wider uppercase">CEO Endpoint:</span>
              <span className="bg-[#25262b] border border-[#2c2e33] text-[#e9ecef] px-2 py-0.5 rounded font-mono text-[10px] uppercase font-bold">
                {ceoModel}
              </span>
            </div>

            <div className="hidden lg:flex items-center gap-2">
              <span className="text-[10px] text-[#909296] font-mono tracking-wider uppercase">Worker Endpoint:</span>
              <span className="bg-[#25262b] border border-[#2c2e33] text-[#e9ecef] px-2 py-0.5 rounded font-mono text-[10px] uppercase font-semibold">
                {workerModel}
              </span>
            </div>

            <button
              id="top-header-run-btn"
              onClick={() => {
                setActiveTab("orchestrator");
                const inputEl = document.getElementById("orchestration-input");
                if (inputEl) inputEl.focus();
              }}
              className="flex items-center gap-1.5 bg-[#20c997] hover:bg-[#1db184] text-[#141517] px-3.5 py-1.5 rounded text-xs font-bold transition-all active:scale-95 cursor-pointer"
            >
              <Sparkles className="w-3.5 h-3.5 shrink-0" />
              New Run
            </button>
          </div>
        </header>

        {/* Tab Selection Area for narrow viewport sizes */}
        <div className="flex md:hidden bg-[#1a1b1e] border-b border-[#2c2e33] p-2 gap-1.5 shrink-0 overflow-x-auto">
          <button
            onClick={() => setActiveTab("orchestrator")}
            className={`px-3 py-1.5 rounded-md text-xs font-semibold ${
              activeTab === "orchestrator" ? "bg-[#2c2e33] text-[#20c997]" : "text-[#909296]"
            }`}
          >
            Play/Orchestrate
          </button>
          <button
            onClick={() => setActiveTab("projects")}
            className={`px-3 py-1.5 rounded-md text-xs font-semibold ${
              activeTab === "projects" ? "bg-[#2c2e33] text-[#20c997]" : "text-[#909296]"
            }`}
          >
            Workspace
          </button>
          <button
            onClick={() => setActiveTab("reports")}
            className={`px-3 py-1.5 rounded-md text-xs font-semibold ${
              activeTab === "reports" ? "bg-[#2c2e33] text-[#20c997]" : "text-[#909296]"
            }`}
          >
            Usage &amp; Spend
          </button>
          <button
            onClick={() => setActiveTab("agents")}
            className={`px-3 py-1.5 rounded-md text-xs font-semibold ${
              activeTab === "agents" ? "bg-[#2c2e33] text-[#20c997]" : "text-[#909296]"
            }`}
          >
            Registry
          </button>
          <button
            onClick={() => setActiveTab("memory")}
            className={`px-3 py-1.5 rounded-md text-xs font-semibold ${
              activeTab === "memory" ? "bg-[#2c2e33] text-[#20c997]" : "text-[#909296]"
            }`}
          >
            Memory
          </button>
        </div>

        {/* 3. SCROLLABLE CONTENTS CONTAINER */}
        <main className="flex-1 p-6 overflow-y-auto w-full max-w-7xl mx-auto">
          {activeTab === "orchestrator" && (
            <Orchestrator onWorkflowCompleted={handleWorkflowCompleted} />
          )}

          {activeTab === "reports" && (
            <UsageDashboard onRefreshTrigger={refreshTrigger} />
          )}

          {activeTab === "projects" && (
            <ProjectWorkspacePanel />
          )}

          {activeTab === "agents" && (
            <div id="agents-tab" className="space-y-6">
              <div className="border-b border-[#2c2e33] pb-5">
                <h1 className="text-xl font-bold tracking-tight text-[#e9ecef] flex items-center gap-2">
                  <Fingerprint className="w-5 h-5 text-[#20c997] animate-pulse" />
                  Active Model Registry
                </h1>
                <p className="text-xs text-[#909296] mt-1 font-sans">
                  Active model nodes available inside TheHiveMind workspace delegation.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {[
                  {
                    name: "CEO Agent",
                    desc: "Reviews corporate prompts, formulates strategic plans, coordinates cluster parameters.",
                    model: "GPT-5.5 Flex",
                    provider: "OpenAI",
                    limits: "Weighted high priority - max 128k input context limit",
                    role: "Master Planner Unit",
                  },
                  {
                    name: "Model Selector Agent",
                    desc: "Analyzes prompt constraints, dynamically routes requests to the cheapest taskforce.",
                    model: "Gemini 3.5 Flash",
                    provider: "Gemini",
                    limits: "Low latency, fast turnarounds · 1M context scope",
                    role: "Routing and Mapping Unit",
                  },
                  {
                    name: "Research Agent",
                    desc: "Executes parallel web grounding queries and extracts academic corpus elements.",
                    model: "Gemini 3.1 Flash-Lite",
                    provider: "Gemini",
                    limits: "Search-integrated operations · $0.03 average search charge",
                    role: "Web Grounding Unit",
                  },
                  {
                    name: "Coding Agent",
                    desc: "Deploys local configuration blueprints and syntax validation tests.",
                    model: "Qwen 2.5 Coder",
                    provider: "OpenRouter",
                    limits: "High instruction fidelity on structured JSON generation",
                    role: "Engineering Unit",
                  },
                  {
                    name: "Content Agent",
                    desc: "Writes localized marketing transcripts and executive highlights.",
                    model: "GPT-5.4 Nano",
                    provider: "OpenAI",
                    limits: "Efficient non-search worker token model",
                    role: "Copywriting Unit",
                  },
                  {
                    name: "QA Agent",
                    desc: "Verifies formatting layouts, syntax rules, and checks logic checks.",
                    model: "GPT-5.4 Nano",
                    provider: "OpenAI",
                    limits: "Validates compliance constraints on outputs",
                    role: "Quality Assurance Unit",
                  }
                ].map((ag, idx) => (
                  <div key={idx} className="bg-[#1a1b1e] border border-[#2c2e33] p-5 rounded-lg space-y-4">
                    <div className="flex items-start justify-between">
                      <div>
                        <span className="text-[10px] text-[#20c997] font-mono tracking-wider uppercase font-semibold">
                          {ag.role}
                        </span>
                        <h3 className="text-sm font-semibold text-[#e9ecef] mt-0.5">{ag.name}</h3>
                      </div>
                      <span className="text-[10px] bg-[#2c2e33] text-[#20c997] border border-[#2c2e33] px-2 py-0.5 rounded font-mono font-bold">
                        {ag.model}
                      </span>
                    </div>

                    <p className="text-xs text-[#909296] leading-relaxed font-sans">
                      {ag.desc}
                    </p>

                    <div className="border-t border-[#2c2e33] pt-3 flex justify-between items-center text-[10px] text-[#909296] font-mono">
                      <span>Provider: <strong className="text-[#e9ecef] capitalize font-medium">{ag.provider}</strong></span>
                      <span>{ag.limits}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeTab === "memory" && (
            <div id="memory-tab" className="space-y-6 max-w-2xl mx-auto my-6">
              <div className="bg-[#20c997]/5 border border-[#20c997]/25 rounded-lg p-6 relative overflow-hidden">
                <div className="absolute right-0 top-0 translate-x-12 -translate-y-12 w-24 h-24 rounded-full bg-[#20c997]/10 blur-[40px] pointer-events-none" />
                <h3 className="text-sm font-bold text-[#20c997] flex items-center gap-1.5 font-mono uppercase mb-2">
                  <Brain className="w-4 h-4 animate-pulse text-[#20c997]" />
                  Context Memory Governance
                </h3>
                <p className="text-xs text-[#e9ecef] leading-relaxed font-sans font-medium">
                  “Agents do not read all memory. They retrieve only the context needed for the active command.”
                </p>
                <p className="text-[11px] text-[#909296] font-mono mt-2 leading-relaxed">
                  In order to optimize token efficiency and prevent distraction, our dual-vector indexing database (Chroma/SQLite) limits prompt ingestion to dynamic K-snippets.
                </p>
              </div>

              <div className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5 space-y-4">
                <h4 className="text-xs font-semibold text-[#909296] tracking-wider uppercase font-mono">Active Memory Corpus</h4>
                
                <div className="space-y-2 text-xs">
                  {[
                    "Core corporate operating benchmarks and business constraints",
                    "Previous 15-turn task outcomes and next actions tables",
                    "Greek Yogurt sector margins, competitors, and marketing rules",
                    "Rust high precision trading routines and rate limit specifications",
                  ].map((doc, idx) => (
                    <div key={idx} className="bg-[#141517] border border-[#2c2e33] p-3 rounded flex items-center justify-between text-[#e9ecef]">
                      <div className="flex items-center gap-2.5">
                        <Database className="w-3.5 h-3.5 text-[#20c997] shrink-0" />
                        <span className="font-sans text-xs">{doc}</span>
                      </div>
                      <span className="text-[9px] text-[#909296] font-mono font-bold select-none uppercase tracking-wide">
                        ACTIVE INDEX
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

    </div>
  );
}
