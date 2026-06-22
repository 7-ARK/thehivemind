import React, { useEffect, useState } from "react";
import { Brain, Search } from "lucide-react";
import { getMemoryStatus, searchProjectMemory } from "../../lib/api";
import { MemorySearchResult, MemoryStatus } from "../../types";

export default function MemoryPanel() {
  const [status, setStatus] = useState<MemoryStatus | null>(null);
  const [projectId, setProjectId] = useState("greek-yogurt-test");
  const [query, setQuery] = useState("Greek yogurt competitors");
  const [agentId, setAgentId] = useState("research_agent");
  const [runType, setRunType] = useState("research_only");
  const [results, setResults] = useState<MemorySearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadStatus() {
    try {
      setStatus(await getMemoryStatus());
    } catch {
      setError("Unable to load memory status.");
    }
  }

  async function runSearch() {
    setLoading(true);
    setError(null);
    try {
      setResults(await searchProjectMemory(projectId, query, agentId, runType));
    } catch {
      setError("Memory search failed.");
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadStatus();
  }, []);

  const project = status?.projects.find((item) => item.project_id === projectId);
  return (
    <div id="memory-tab" className="space-y-6">
      <section className="border-b border-[#2c2e33] pb-5">
        <h1 className="text-xl font-bold tracking-tight text-[#e9ecef] flex items-center gap-2">
          <Brain className="w-5 h-5 text-[#20c997]" />
          Vector Memory v1
        </h1>
        <p className="text-xs text-[#909296] mt-1">Local sparse retrieval for project state, run summaries, research sources, model choices, and QA warnings.</p>
      </section>

      {error && <div className="bg-rose-500/10 border border-rose-500/30 text-rose-300 rounded-lg p-4 text-xs">{error}</div>}

      <section className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Metric label="Enabled" value={String(Boolean(status?.enabled))} />
        <Metric label="Backend" value={status?.backend_mode ?? "loading"} />
        <Metric label="Total Items" value={String(status?.total_memory_items ?? 0)} />
        <Metric label="Project Items" value={String(project?.memory_count ?? 0)} />
      </section>

      <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5 space-y-4">
        <h2 className="text-sm font-bold text-[#e9ecef] flex items-center gap-2">
          <Search className="w-4 h-4 text-[#20c997]" />
          Test Retrieval
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-3">
          <Field label="Project ID"><input className="control-input" value={projectId} onChange={(event) => setProjectId(event.target.value)} /></Field>
          <Field label="Agent"><input className="control-input" value={agentId} onChange={(event) => setAgentId(event.target.value)} /></Field>
          <Field label="Run Type"><input className="control-input" value={runType} onChange={(event) => setRunType(event.target.value)} /></Field>
          <button onClick={runSearch} disabled={loading || !query.trim()} className="self-end bg-[#20c997] hover:bg-[#1db184] disabled:bg-[#2c2e33] text-[#141517] text-sm font-bold px-4 py-3 rounded">
            {loading ? "Searching..." : "Search Memory"}
          </button>
        </div>
        <textarea className="control-input min-h-24" value={query} onChange={(event) => setQuery(event.target.value)} />
      </section>

      <section className="space-y-3">
        {results.length === 0 ? (
          <div className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4 text-xs text-[#909296]">No retrieval results yet.</div>
        ) : (
          results.map((result) => (
            <div key={result.item.id} className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-bold text-[#e9ecef]">{result.item.title}</h3>
                  <p className="text-[10px] text-[#909296] font-mono mt-1">{result.item.memory_type} / score {result.score.toFixed(3)}</p>
                </div>
                <span className="text-[10px] text-[#20c997] font-mono">{result.why_selected.join(", ")}</span>
              </div>
              <p className="text-xs text-[#ced4da] mt-3">{result.item.summary || result.item.content}</p>
              {result.item.source_urls.length > 0 && <p className="text-[10px] text-[#909296] mt-2 font-mono">{result.item.source_urls.slice(0, 3).join(" | ")}</p>}
            </div>
          ))
        )}
      </section>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[10px] text-[#909296] uppercase tracking-wider font-mono">{label}</span>
      <div className="mt-2">{children}</div>
    </label>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-4">
      <div className="text-[10px] uppercase tracking-wider font-mono text-[#909296]">{label}</div>
      <div className="text-lg text-[#e9ecef] font-mono font-bold mt-2 truncate">{value}</div>
    </div>
  );
}
