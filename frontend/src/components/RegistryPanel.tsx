import React, { useEffect, useState } from "react";
import { Cpu, Database, ChevronDown, Search } from "lucide-react";
import { getAgentRegistry, getModelRegistryModels, getModelRegistrySummary, getOpenRouterDiscoverySummary, getSearchToolsStatus } from "../lib/api";
import { AgentRegistryEntry, ModelRegistryModel, OpenRouterDiscoverySummary, SearchToolsStatus } from "../types";

export default function RegistryPanel() {
  const [agents, setAgents] = useState<AgentRegistryEntry[]>([]);
  const [models, setModels] = useState<ModelRegistryModel[]>([]);
  const [summary, setSummary] = useState<Record<string, any>>({});
  const [searchStatus, setSearchStatus] = useState<SearchToolsStatus | null>(null);
  const [openRouterSummary, setOpenRouterSummary] = useState<OpenRouterDiscoverySummary | null>(null);
  const [openModel, setOpenModel] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getAgentRegistry(), getModelRegistryModels(), getModelRegistrySummary(), getSearchToolsStatus(), getOpenRouterDiscoverySummary()])
      .then(([agentPayload, modelPayload, registrySummary, searchPayload, discoveryPayload]) => {
        setAgents(agentPayload.agents);
        setModels(modelPayload.models);
        setSummary(registrySummary);
        setSearchStatus(searchPayload);
        setOpenRouterSummary(discoveryPayload);
      })
      .catch(() => {
        setAgents([]);
        setModels([]);
      });
  }, []);

  return (
    <div id="agents-tab" className="space-y-6">
      <div className="border-b border-[#2c2e33] pb-5">
        <h1 className="text-xl font-bold tracking-tight text-[#e9ecef] flex items-center gap-2">
          <Cpu className="w-5 h-5 text-[#20c997]" />
          Model & Agent Registry
        </h1>
        <p className="text-xs text-[#909296] mt-1">
          Controlled registry used by the planner and dynamic model selector. GPT-5.5 remains blocked unless approved.
        </p>
      </div>

      <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5">
        <h2 className="text-sm font-bold text-[#e9ecef] flex items-center gap-2">
          <Database className="w-4 h-4 text-[#20c997]" />
          Model Registry
        </h2>
        <p className="text-xs text-[#909296] mt-1">
          {summary.models_count ?? models.length} models across {(summary.providers ?? []).join(", ") || "configured providers"}.
          {" "}OpenRouter discovery cache: {openRouterSummary?.cached_models_count ?? summary.openrouter_discovery?.cached_models_count ?? 0} metadata models.
        </p>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mt-4">
          {models.map((model) => (
            <div key={model.id} className="bg-[#141517] border border-[#2c2e33] rounded p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="text-sm font-bold text-[#e9ecef]">{model.display_name}</h3>
                  <p className="text-[10px] text-[#909296] font-mono mt-1">{model.provider} / {model.status} / {model.cost_level}</p>
                </div>
                <span className={model.requires_approval ? "text-[#fab005] text-[10px] font-mono" : "text-[#20c997] text-[10px] font-mono"}>
                  {model.requires_approval ? "approval" : "ready"}
                </span>
              </div>
              <div className="flex flex-wrap gap-2 text-[10px] font-mono mt-3">
                <CapabilityTags
                  items={[
                    ["native search", model.supports_web_search],
                    ["vision", model.supports_vision],
                    ["tools", model.supports_tool_use],
                    ["json", model.supports_json],
                  ]}
                />
                {model.search_tool_compatible && <Tag active>external search compatible</Tag>}
              </div>
              <p className="text-xs text-[#909296] mt-3">{model.best_for?.slice(0, 2).join(", ") || "General controlled worker use."}</p>
              <button onClick={() => setOpenModel(openModel === model.id ? null : model.id)} className="mt-3 text-[10px] text-[#20c997] font-mono flex items-center gap-1">
                <ChevronDown className="w-3 h-3" />
                Details
              </button>
              {openModel === model.id && (
                <div className="mt-3 border-t border-[#2c2e33] pt-3 text-xs text-[#909296] space-y-2">
                  <p>Fallback: {model.fallback_models?.join(", ") || "none"}</p>
                  <p>Default roles: {model.default_agent_roles?.join(", ") || "none"}</p>
                  <p>Strengths: {model.known_strengths?.join(", ") || "unknown"}</p>
                  <p>Limitations: {model.known_limitations?.join(", ") || "unknown"}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5">
        <h2 className="text-sm font-bold text-[#e9ecef] flex items-center gap-2">
          <Search className="w-4 h-4 text-[#20c997]" />
          Search Provider Registry
        </h2>
        <p className="text-xs text-[#909296] mt-1">
          Search is selected separately from model routing. OpenRouter discovery is metadata-only and never appears here.
        </p>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 mt-4">
          {(searchStatus?.providers ?? []).map((provider) => (
            <div key={provider.id} className="bg-[#141517] border border-[#2c2e33] rounded p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="text-sm font-bold text-[#e9ecef]">{provider.display_name}</h3>
                  <p className="text-[10px] text-[#909296] font-mono mt-1">{provider.id} / {provider.provider}</p>
                </div>
                <span className={provider.live_search_available ? "text-[#20c997] text-[10px] font-mono" : "text-[#fab005] text-[10px] font-mono"}>
                  {provider.live_search_available ? "live ready" : "live guarded"}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-[10px] font-mono mt-3">
                <StatusPill active={provider.configured}>configured</StatusPill>
                <StatusPill active={provider.mock_fixture_available}>mock fixture</StatusPill>
                <StatusPill active={provider.available_for_live}>provider live</StatusPill>
                <StatusPill active={provider.live_search_available}>search live</StatusPill>
              </div>
              <div className="flex flex-wrap gap-2 text-[10px] font-mono mt-3">
                <CapabilityTags
                  items={[
                    ["semantic", provider.supports_semantic_search],
                    ["content", provider.supports_content_extraction],
                    ["google", provider.supports_google_grounding],
                    ["answer", provider.supports_answer_generation],
                  ]}
                />
              </div>
              <p className="text-xs text-[#909296] mt-3">{provider.best_for?.slice(0, 2).join(", ") || "Controlled research provider."}</p>
              {provider.reasons?.length > 0 && <p className="text-[10px] text-[#fab005] mt-2">{provider.reasons.join(" ")}</p>}
            </div>
          ))}
        </div>
      </section>

      <section className="bg-[#1a1b1e] border border-[#2c2e33] rounded-lg p-5">
        <h2 className="text-sm font-bold text-[#e9ecef]">Agent Registry</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mt-4">
          {agents.map((agent) => (
            <div key={agent.id} className="bg-[#141517] border border-[#2c2e33] rounded p-4">
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-sm font-bold text-[#e9ecef]">{agent.display_name}</h3>
                <span className="text-[10px] text-[#20c997] font-mono">{agent.status}</span>
              </div>
              <p className="text-xs text-[#909296] mt-2">{agent.purpose}</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3 text-[10px] font-mono text-[#909296]">
                <p>Tools: {agent.allowed_tools.join(", ") || "none"}</p>
                <p>Models: {agent.default_models.join(", ") || "none"}</p>
                <p>Allowed: {agent.allowed_actions.join(", ") || "none"}</p>
                <p>Blocked: {agent.blocked_actions.join(", ") || "none"}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Tag({ active, children }: { active: boolean; children: React.ReactNode }) {
  return <span className={active ? "text-[#20c997]" : "text-[#909296]"}>{children}</span>;
}

function CapabilityTags({ items }: { items: Array<[string, boolean]> }) {
  const activeItems = items.filter(([, active]) => active);
  if (activeItems.length === 0) return <Tag active={false}>no native extras</Tag>;
  return (
    <>
      {activeItems.map(([label]) => (
        <React.Fragment key={label}>
          <Tag active>{label}</Tag>
        </React.Fragment>
      ))}
    </>
  );
}

function StatusPill({ active, children }: { active: boolean; children: React.ReactNode }) {
  return (
    <span className={active ? "text-[#20c997] border border-[#20c997]/20 bg-[#20c997]/10 rounded px-2 py-1" : "text-[#909296] border border-[#2c2e33] bg-[#25262b] rounded px-2 py-1"}>
      {children}
    </span>
  );
}
