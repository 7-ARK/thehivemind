import {
  UsageSummary,
  ProviderUsage,
  ModelUsage,
  AgentUsage,
  UsageTimeSeriesPoint,
  RecentCall,
  ExpensiveRun,
  BudgetStatus,
  SearchUsageType,
  TokenBreakdownType,
  OfficialUsageSummary,
  RealUsageSummary,
  RealProviderUsageRecord,
  RealOfficialBillingRecord,
  OrchestrationResult,
  CompletedAgentStep,
  OrchestratePlanStep,
  ProjectWorkspace,
  ProjectManifest,
  ProjectFile,
  ProjectChange,
  CommandResult,
  ArtifactRecord,
  CreateRunPayload,
  ApprovalRequest,
  RunStartResponse,
  RunResult,
  AgentPlan,
  AgentRegistryEntry,
  ModelRegistryModel,
  MemorySearchResult,
  MemoryStatus,
  SearchLogRecord,
  SearchToolsStatus,
  OpenRouterDiscoverySummary,
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

type BackendRunEvent = {
  timestamp: string;
  agent_name: string;
  agent_role: string;
  status: string;
  action_summary: string;
  input_summary: string;
  output_summary: string;
  model_used: string;
  estimated_input_tokens: number;
  estimated_output_tokens: number;
  estimated_cost_usd: number;
};

type BackendRunRecord = {
  run_id: string;
  command: string;
  mode: "mock" | "live";
  status: string;
  started_at: string;
  completed_at: string | null;
  events: BackendRunEvent[];
  metrics: {
    total_estimated_tokens: number;
    total_estimated_cost_usd: number;
    run_duration_seconds: number;
    memory_chunks_retrieved: number;
  };
  memory: {
    retrieved_snippets: Array<{ title: string; content: string; relevance_score: number }>;
  };
  final_output: {
    summary: string;
    what_was_done: string[];
    recommended_next_actions: string[];
    generated_artifacts: string[];
  };
};

type ProviderStatus = {
  providers: Record<string, { configured: boolean; search_enabled: boolean }>;
  live_calls_allowed: boolean;
  default_models: Record<string, string | null>;
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    let detail = `API request failed: ${response.status}`;
    try {
      const payload = await response.json();
      detail = formatBackendErrorDetail(payload.detail ?? detail);
    } catch {
      // Keep the status-based detail.
    }
    throw new Error(String(detail));
  }

  return response.json() as Promise<T>;
}

function formatBackendErrorDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const record = detail as Record<string, unknown>;
    if (typeof record.message === "string") return record.message;
    if (typeof record.error === "string") return record.error;
    try {
      return JSON.stringify(detail);
    } catch {
      return "Backend request failed with an unreadable error detail.";
    }
  }
  return String(detail);
}

export async function getHealth(): Promise<{ status: string; environment: string; mock_mode: boolean }> {
  return request("/health");
}

export async function getProviderStatus(): Promise<ProviderStatus> {
  return request("/api/providers/status");
}

export async function getUsageSummary(range: string = "30d"): Promise<UsageSummary> {
  const summary = await request<{
    total_calls: number;
    failed_calls: number;
    success_rate: number;
    total_tokens: number;
    effective_cost_usd: number;
    total_estimated_cost_usd: number;
    average_latency_ms: number;
    p95_latency_ms: number;
    total_cached_tokens: number;
    cached_token_savings_usd: number;
    search_calls: number;
    search_cost_usd: number;
  }>(`/api/usage/summary?range=${encodeURIComponent(range)}`);

  return {
    totalCost: summary.effective_cost_usd ?? summary.total_estimated_cost_usd,
    totalCalls: summary.total_calls,
    totalTokens: summary.total_tokens,
    successRate: summary.success_rate,
    averageLatency: summary.average_latency_ms,
    p95Latency: summary.p95_latency_ms,
    failedCalls: summary.failed_calls,
    cachedTokenSavings: summary.total_cached_tokens,
    cachedCostSavings: summary.cached_token_savings_usd,
    searchCalls: summary.search_calls,
    searchCost: summary.search_cost_usd,
  };
}

export async function getUsageProviders(range: string = "30d"): Promise<ProviderUsage[]> {
  const payload = await request<{
    providers: Array<{
      provider: string;
      calls: number;
      input_tokens: number;
      output_tokens: number;
      cached_tokens: number;
      cost_usd: number;
      avg_latency_ms: number;
      success_rate: number;
      failed_calls: number;
    }>;
  }>(`/api/usage/providers?range=${encodeURIComponent(range)}`);

  return payload.providers.map((provider) => ({
    provider: labelProvider(provider.provider),
    cost: provider.cost_usd,
    calls: provider.calls,
    tokens: provider.input_tokens + provider.output_tokens + provider.cached_tokens,
    averageLatency: provider.avg_latency_ms,
    successRate: provider.success_rate,
    failedCalls: provider.failed_calls,
  }));
}

export async function getUsageModels(range: string = "30d"): Promise<ModelUsage[]> {
  const payload = await request<{
    models: Array<{
      model: string;
      provider: string;
      role: string;
      calls: number;
      input_tokens: number;
      output_tokens: number;
      cost_usd: number;
      avg_cost_per_call: number;
      success_rate: number;
    }>;
  }>(`/api/usage/models?range=${encodeURIComponent(range)}`);

  return payload.models.map((model) => ({
    model: labelModel(model.model),
    provider: labelProvider(model.provider),
    role: model.role,
    cost: model.cost_usd,
    calls: model.calls,
    inputTokens: model.input_tokens,
    outputTokens: model.output_tokens,
    averageCostPerCall: model.avg_cost_per_call,
    successRate: model.success_rate,
  }));
}

export async function getUsageAgents(range: string = "30d"): Promise<AgentUsage[]> {
  const payload = await request<{
    agents: Array<{
      agent_name: string;
      model: string;
      provider: string;
      calls: number;
      cost_usd: number;
      tokens: number;
      avg_latency_ms: number;
      success_rate: number;
    }>;
  }>(`/api/usage/agents?range=${encodeURIComponent(range)}`);

  return payload.agents.map((agent) => ({
    agent: agent.agent_name,
    cost: agent.cost_usd,
    tokens: agent.tokens,
    calls: agent.calls,
    primaryModel: labelModel(agent.model),
    provider: labelProvider(agent.provider),
    successRate: agent.success_rate,
    averageLatency: agent.avg_latency_ms,
  }));
}

export async function getUsageTimeSeries(range: string = "30d"): Promise<UsageTimeSeriesPoint[]> {
  const payload = await request<{
    points: Array<{
      date: string;
      calls: number;
      cost_usd: number;
      input_tokens: number;
      output_tokens: number;
      failed_calls: number;
    }>;
  }>(`/api/usage/timeseries?range=${encodeURIComponent(range)}&bucket=day`);

  return payload.points.map((point) => ({
    date: point.date,
    cost: point.cost_usd,
    calls: point.calls,
    tokens: point.input_tokens + point.output_tokens,
    failedCalls: point.failed_calls,
  }));
}

export async function getUsageRecent(limit: number = 20): Promise<RecentCall[]> {
  const payload = await request<{
    recent_calls: Array<{
      id?: string;
      timestamp: string;
      provider: string;
      model: string;
      agent: string;
      request_type: string;
      success: boolean;
      input_tokens: number;
      output_tokens: number;
      cost_usd: number;
      latency_ms: number;
      error_message?: string | null;
    }>;
  }>(`/api/usage/recent?limit=${limit}`);

  return payload.recent_calls.map((call, index) => ({
    id: call.id ?? `${new Date(call.timestamp).getTime()}-${index}`,
    time: formatDateTime(call.timestamp),
    provider: labelProvider(call.provider),
    model: labelModel(call.model),
    agent: call.agent,
    requestType: call.request_type,
    inputTokens: call.input_tokens,
    outputTokens: call.output_tokens,
    cost: call.cost_usd,
    latency: call.latency_ms,
    status: call.success ? "success" : "failed",
    errorMessage: call.error_message ?? undefined,
  }));
}

export async function getExpensiveRuns(limit: number = 10): Promise<ExpensiveRun[]> {
  const payload = await request<{
    runs: Array<{
      run_id: string;
      title?: string;
      total_cost_usd: number;
      total_tokens: number;
      providers_used: string[];
      models_used: string[];
      agents_used: string[];
      call_count: number;
      failed_calls: number;
      run_timestamp: string;
    }>;
  }>(`/api/usage/expensive-runs?limit=${limit}`);

  return payload.runs.map((run) => ({
    id: run.run_id,
    title: run.title ?? `Run ${run.run_id}`,
    cost: run.total_cost_usd,
    totalTokens: run.total_tokens,
    providers: run.providers_used.map(labelProvider),
    models: run.models_used.map(labelModel),
    agents: run.agents_used,
    callCount: run.call_count,
    failedCalls: run.failed_calls,
    timestamp: formatDateTime(run.run_timestamp),
  }));
}

export async function getUsageBudget(range: string = "30d"): Promise<BudgetStatus> {
  const budget = await request<{
    monthly_budget_usd: number;
    daily_budget_usd: number;
    spent_usd: number;
    remaining_usd: number;
    percent_used: number;
    status: BudgetStatus["status"];
  }>(`/api/usage/budget?range=${encodeURIComponent(range)}`);

  return {
    monthlyBudget: range === "today" ? budget.daily_budget_usd : budget.monthly_budget_usd,
    spent: budget.spent_usd,
    remaining: budget.remaining_usd,
    percentUsed: budget.percent_used,
    status: budget.status,
  };
}

export async function getUsageSearch(range: string = "30d"): Promise<SearchUsageType> {
  const search = await request<{
    total_search_calls: number;
    search_cost_usd: number;
    search_by_provider: Record<string, number>;
    search_by_agent: Record<string, number>;
    status: string;
  }>(`/api/usage/search?range=${encodeURIComponent(range)}`);

  return {
    searchCalls: search.total_search_calls,
    searchCost: search.search_cost_usd,
    status: search.status,
    searchByProvider: Object.fromEntries(
      Object.entries(search.search_by_provider).map(([provider, calls]) => [labelProvider(provider), calls]),
    ),
    searchByAgent: search.search_by_agent,
  };
}

export async function getUsageTokens(range: string = "30d"): Promise<TokenBreakdownType> {
  const payload = await request<{
    models: Array<{
      input_tokens: number;
      output_tokens: number;
      cached_tokens: number;
      reasoning_tokens: number;
    }>;
  }>(`/api/usage/tokens?range=${encodeURIComponent(range)}`);

  return payload.models.reduce(
    (total, model) => ({
      inputTokens: total.inputTokens + model.input_tokens,
      outputTokens: total.outputTokens + model.output_tokens,
      cachedTokens: total.cachedTokens + model.cached_tokens,
      reasoningTokens: total.reasoningTokens + model.reasoning_tokens,
    }),
    { inputTokens: 0, outputTokens: 0, cachedTokens: 0, reasoningTokens: 0 },
  );
}

export async function getOfficialUsageSummary(range: string = "30d"): Promise<OfficialUsageSummary> {
  return request<OfficialUsageSummary>(`/api/official-usage/summary?range=${encodeURIComponent(range)}`);
}

export async function syncOfficialUsage(range: string = "30d"): Promise<OfficialUsageSummary> {
  const payload = await request<{ status: OfficialUsageSummary["status"]; synced: Record<string, number> }>(`/api/official-usage/sync?range=${encodeURIComponent(range)}`, {
    method: "POST",
  });
  const summary = await getOfficialUsageSummary(range);
  return { ...summary, status: payload.status };
}

export async function getRealUsageSummary(): Promise<RealUsageSummary> {
  return request<RealUsageSummary>("/api/usage/real/summary");
}

export async function getRealProviderResponses(limit: number = 100): Promise<RealProviderUsageRecord[]> {
  const payload = await request<{ records: RealProviderUsageRecord[] }>(`/api/usage/real/provider-responses?limit=${limit}`);
  return payload.records;
}

export async function getRealAccountBilling(): Promise<{ records: RealOfficialBillingRecord[]; note: string }> {
  return request<{ records: RealOfficialBillingRecord[]; note: string }>("/api/usage/official/account-billing");
}

export async function seedDemoUsage(): Promise<{ status: string; message: string }> {
  const payload = await request<{ inserted: number }>("/api/usage/seed-demo", { method: "POST" });
  return {
    status: "success",
    message: `Seeded ${payload.inserted} telemetry rows in the backend database.`,
  };
}

export function exportUsageCsvUrl(range: string = "30d"): string {
  return `${API_BASE_URL}/api/usage/export.csv?range=${encodeURIComponent(range)}`;
}

export async function submitOrchestration(command: string): Promise<OrchestrationResult> {
  const run = await createRun({
    command,
    mode: "mock",
    project_id: "greek-yogurt-test",
    run_type: "prototype_build",
    allow_file_writes: true,
    allow_safe_commands: true,
    allow_web_search: false,
    allow_ceo_live: false,
    use_memory: true,
    use_real_coding_agent: true,
    allow_live_coding_model_call: false,
    real_coding_dry_run: false,
    real_coding_model: "moonshotai/kimi-k2.7-code",
    real_coding_max_files: 12,
    real_coding_max_repair_attempts: 0,
    max_cost_usd: 0.25,
  });

  if (isApprovalRequiredResponse(run)) {
    throw new Error("Approval is required before this orchestration can run.");
  }
  return mapRunToOrchestration(run);
}

export async function createRun(payload: CreateRunPayload): Promise<RunStartResponse> {
  return request<RunStartResponse>("/api/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function decideApproval(approvalId: string, decision: "approved" | "rejected", reason?: string): Promise<ApprovalRequest> {
  return request<ApprovalRequest>(`/api/approvals/${encodeURIComponent(approvalId)}/decision`, {
    method: "POST",
    body: JSON.stringify({ decision, reason }),
  });
}

export async function getPendingApprovals(): Promise<ApprovalRequest[]> {
  return request("/api/approvals/pending");
}

export async function getRun(runId: string): Promise<RunResult> {
  return request(`/api/runs/${encodeURIComponent(runId)}`);
}

export async function getRunEvents(runId: string): Promise<RunResult["events"]> {
  return request(`/api/runs/${encodeURIComponent(runId)}/events`);
}

export async function getProject(projectId: string): Promise<ProjectWorkspace> {
  return request(`/api/projects/${encodeURIComponent(projectId)}`);
}

export async function getProjectState(projectId: string): Promise<{ project_id: string; path: string; content: string }> {
  return request(`/api/projects/${encodeURIComponent(projectId)}/state`);
}

export async function getProjectManifest(projectId: string): Promise<ProjectManifest> {
  return request(`/api/projects/${encodeURIComponent(projectId)}/manifest`);
}

export async function getProjectFiles(projectId: string): Promise<ProjectFile[]> {
  return request(`/api/projects/${encodeURIComponent(projectId)}/files`);
}

export async function getProjectFile(projectId: string, path: string): Promise<{ project_id: string; path: string; content: string }> {
  return request(`/api/projects/${encodeURIComponent(projectId)}/files/${encodeProjectPath(path)}`);
}

export async function getProjectRuns(projectId: string): Promise<{ project_id: string; runs: ProjectManifest["runs"] }> {
  return request(`/api/projects/${encodeURIComponent(projectId)}/runs`);
}

export async function getProjectChanges(projectId: string): Promise<{ project_id: string; changes: ProjectChange[] }> {
  return request(`/api/projects/${encodeURIComponent(projectId)}/changes`);
}

export function projectPrototypePreviewUrl(projectId: string, runId: string): string {
  return `${API_BASE_URL}/api/projects/${encodeURIComponent(projectId)}/prototypes/${encodeURIComponent(runId)}/preview`;
}

export async function getRunWorkspaceFiles(runId: string): Promise<{ run_id: string; files: Array<Record<string, unknown>> }> {
  return request(`/api/runs/${encodeURIComponent(runId)}/workspace/files`);
}

export async function getRunCommands(runId: string): Promise<CommandResult[]> {
  return request(`/api/runs/${encodeURIComponent(runId)}/commands`);
}

export async function getRunArtifacts(runId: string): Promise<ArtifactRecord[]> {
  return request(`/api/runs/${encodeURIComponent(runId)}/artifacts`);
}

export async function getRunAgentPlan(runId: string): Promise<{ run_id: string; agent_plan: AgentPlan | Record<string, unknown> }> {
  return request(`/api/runs/${encodeURIComponent(runId)}/agent-plan`);
}

export async function getRunModelSelection(runId: string): Promise<{ run_id: string; model_selection: Record<string, any> }> {
  return request(`/api/runs/${encodeURIComponent(runId)}/model-selection`);
}

export async function getAgentRegistry(): Promise<{ agents: AgentRegistryEntry[] }> {
  return request("/api/agent-registry/agents");
}

export async function getModelRegistryModels(): Promise<{ models: ModelRegistryModel[] }> {
  return request("/api/model-registry/models");
}

export async function getModelRegistrySummary(): Promise<Record<string, any>> {
  return request("/api/model-registry/summary");
}

export async function getSearchToolsStatus(): Promise<SearchToolsStatus> {
  return request("/api/search-tools/status");
}

export async function getRecentSearchLogs(limit: number = 100): Promise<SearchLogRecord[]> {
  const payload = await request<{ logs: SearchLogRecord[] }>(`/api/search-tools/logs/recent?limit=${limit}`);
  return payload.logs;
}

export async function getMemoryStatus(): Promise<MemoryStatus> {
  return request<MemoryStatus>("/api/memory/status");
}

export async function searchProjectMemory(projectId: string, query: string, agentId: string, runType: string): Promise<MemorySearchResult[]> {
  const params = new URLSearchParams({ q: query, agent_id: agentId, run_type: runType });
  const payload = await request<{ results: MemorySearchResult[] }>(`/api/memory/projects/${encodeURIComponent(projectId)}/search?${params.toString()}`);
  return payload.results;
}

export async function getOpenRouterDiscoverySummary(): Promise<OpenRouterDiscoverySummary> {
  return request("/api/model-registry/discovery/openrouter/summary");
}

function isApprovalRequiredResponse(run: RunStartResponse): run is import("../types").ApprovalRequiredResponse {
  return "approval_requests" in run && run.status === "approval_required";
}

function encodeProjectPath(path: string): string {
  return path.split("/").map(encodeURIComponent).join("/");
}

function mapRunToOrchestration(run: BackendRunRecord | RunResult): OrchestrationResult {
  const agentEvents = run.events.filter((event) => event.agent_name !== "TheHiveMind");
  const agentSteps: CompletedAgentStep[] = agentEvents.map((event) => ({
    agent: normalizeAgentName(event.agent_name),
    action: event.action_summary,
    content: event.output_summary,
    tokens: event.estimated_input_tokens + event.estimated_output_tokens,
    cost: event.estimated_cost_usd,
    latency: estimateStepLatency(run),
  }));
  const planSteps: OrchestratePlanStep[] = agentEvents.map((event, index) => ({
    step: index + 1,
    title: event.action_summary,
    agent: normalizeAgentName(event.agent_name),
    model: labelModel(event.model_used),
  }));

  return {
    runId: run.run_id,
    timestamp: formatDateTime(run.started_at),
    command: run.command,
    ceoPlan: {
      title: `Strategic Plan: ${run.command}`,
      steps: planSteps,
      executiveSummary: run.final_output.summary,
    },
    agentSteps,
    tokensUsed: run.metrics.total_estimated_tokens,
    cost: run.metrics.total_estimated_cost_usd,
    memoryUsed: {
      snippets: run.memory.retrieved_snippets.map((snippet) => `[${snippet.title}]: ${snippet.content}`),
      numChunks: run.metrics.memory_chunks_retrieved,
    },
    finalReport: buildFinalReport(run),
    nextActions: run.final_output.recommended_next_actions,
  };
}

function buildFinalReport(run: BackendRunRecord | RunResult): string {
  const artifacts = run.final_output.generated_artifacts.map((item) => `- ${item}`).join("\n");
  const work = run.final_output.what_was_done.map((item) => `- ${item}`).join("\n");
  const next = run.final_output.recommended_next_actions.map((item) => `- ${item}`).join("\n");

  return `### THEHIVEMIND DISPATCH: ${run.command.toUpperCase()}
**Status:** ${run.status}
**Run ID:** \`${run.run_id}\`
**Mode:** ${run.mode}

#### Executive Summary
${run.final_output.summary}

#### Workflow Accomplishments
${work}

#### Financial & Token Telemetry
- Total estimated spend: \`$${run.metrics.total_estimated_cost_usd.toFixed(6)}\`
- Total estimated tokens: \`${run.metrics.total_estimated_tokens.toLocaleString()}\`
- Runtime: \`${run.metrics.run_duration_seconds}s\`
- Memory chunks retrieved: \`${run.metrics.memory_chunks_retrieved}\`

#### Generated Artifacts
${artifacts}

#### Recommended Next Actions
${next}
`;
}

function estimateStepLatency(run: BackendRunRecord | RunResult): number {
  return Math.max(1, Math.round((run.metrics.run_duration_seconds * 1000) / Math.max(1, run.events.length)));
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function labelProvider(provider: string | null | undefined): string {
  const value = provider ?? "unknown";
  const labels: Record<string, string> = {
    openai: "OpenAI",
    gemini: "Gemini",
    openrouter: "OpenRouter",
    mock: "Mock",
    unknown: "Unknown",
  };
  return labels[value.toLowerCase()] ?? value;
}

function labelModel(model: string | null | undefined): string {
  const value = model ?? "unassigned";
  const labels: Record<string, string> = {
    "gpt-5.5": "GPT-5.5",
    "gpt-5.4-nano": "GPT-5.4 Nano",
    "gemini-3.5-flash": "Gemini 3.5 Flash",
    "gemini-3.1-flash-lite": "Gemini 3.1 Flash-Lite",
    "qwen/qwen3-coder": "Qwen 3 Coder",
  };
  return labels[value.toLowerCase()] ?? value;
}

function normalizeAgentName(agent: string): string {
  return agent === "Model Selector Agent" ? "Model Selector" : agent;
}
