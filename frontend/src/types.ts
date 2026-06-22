export interface UsageSummary {
  totalCost: number;
  totalCalls: number;
  totalTokens: number;
  successRate: number;
  averageLatency: number;
  p95Latency: number;
  failedCalls: number;
  cachedTokenSavings: number;
  cachedCostSavings: number;
  searchCalls: number;
  searchCost: number;
}

export interface BudgetStatus {
  monthlyBudget: number;
  spent: number;
  remaining: number;
  percentUsed: number;
  status: "safe" | "warning" | "danger" | "exceeded";
}

export interface ProviderUsage {
  provider: string;
  cost: number;
  calls: number;
  tokens: number;
  averageLatency: number;
  successRate: number;
  failedCalls: number;
}

export interface ModelUsage {
  model: string;
  provider: string;
  role: string;
  cost: number;
  calls: number;
  inputTokens: number;
  outputTokens: number;
  averageCostPerCall: number;
  successRate: number;
}

export interface AgentUsage {
  agent: string;
  cost: number;
  tokens: number;
  calls: number;
  primaryModel: string;
  provider: string;
  successRate: number;
  averageLatency: number;
}

export interface UsageTimeSeriesPoint {
  date: string;
  cost: number;
  calls: number;
  tokens: number;
  failedCalls: number;
}

export interface RecentCall {
  id: string;
  time: string;
  provider: string;
  model: string;
  agent: string;
  requestType: string;
  inputTokens: number;
  outputTokens: number;
  cost: number;
  latency: number;
  status: "success" | "failed";
  errorMessage?: string;
}

export interface ExpensiveRun {
  id: string;
  title: string;
  cost: number;
  totalTokens: number;
  providers: string[];
  models: string[];
  agents: string[];
  callCount: number;
  failedCalls: number;
  timestamp: string;
}

export interface TokenBreakdownType {
  inputTokens: number;
  outputTokens: number;
  cachedTokens: number;
  reasoningTokens: number;
}

export interface SearchUsageType {
  searchCalls: number;
  searchCost: number;
  status: string;
  searchByProvider: Record<string, number>;
  searchByAgent: Record<string, number>;
}

export interface OfficialUsageProviderStatus {
  enabled: boolean;
  admin_key_configured?: boolean;
  management_key_configured?: boolean;
  credentials_configured?: boolean;
  api_key_configured?: boolean;
  service_key_configured?: boolean;
  api_key_id_configured?: boolean;
  project_id?: string;
  dataset?: string;
  location?: string;
  tables_found?: number;
  last_synced_at?: string | null;
  status: string;
  message?: string | null;
}

export interface OfficialUsageReconciliation {
  provider: string;
  range: string;
  scope: string;
  safety_estimated_cost_usd: number;
  provider_reported_cost_usd?: number | null;
  status: "mock_only" | "estimated" | "provider_reported" | "reconciled" | "unavailable" | "error";
  last_synced_at?: string | null;
  notes: string[];
}

export interface OfficialUsageSummary {
  range: string;
  status: Record<string, OfficialUsageProviderStatus>;
  reconciliation: OfficialUsageReconciliation[];
}

export interface RealUsageSummary {
  run_level_provider_cost_usd: number;
  model_provider_reported_cost_usd?: number;
  search_tool_estimated_cost_usd?: number;
  run_level_tokens: number;
  run_level_calls: number;
  official_billing_cost_usd: number;
  unknown_provider_cost_count?: number;
  account_balance_records: number;
  providers: string[];
  run_level_providers?: string[];
  official_providers?: string[];
  cost_labels_explained?: Record<string, string>;
  dev_estimates_hidden: boolean;
  note: string;
}

export interface RealProviderUsageRecord {
  id: string;
  run_id?: string | null;
  project_id?: string | null;
  provider: string;
  requested_model?: string | null;
  actual_model?: string | null;
  provider_name?: string | null;
  agent_name?: string | null;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  reasoning_tokens: number;
  total_tokens: number;
  provider_reported_cost_usd?: number | null;
  source: "provider_response" | "provider_generation_lookup" | "mock_dev_only" | "safety_estimate_dev_only";
  sync_status?: string | null;
  timestamp?: string | null;
}

export interface RealOfficialBillingRecord {
  id: string;
  provider: string;
  source: "provider_official_billing" | "provider_account_balance";
  scope: string;
  project_id?: string | null;
  service?: string | null;
  sku?: string | null;
  provider_reported_cost_usd?: number | null;
  currency: string;
  usage_start_time?: string | null;
  usage_end_time?: string | null;
  created_at: string;
  note: string;
}

export interface OrchestratePlanStep {
  step: number;
  title: string;
  agent: string;
  model: string;
}

export interface CompletedAgentStep {
  agent: string;
  action: string;
  content: string;
  tokens: number;
  cost: number;
  latency: number;
}

export interface OrchestrationResult {
  runId: string;
  timestamp: string;
  command: string;
  ceoPlan: {
    title: string;
    steps: OrchestratePlanStep[];
    executiveSummary: string;
  };
  agentSteps: CompletedAgentStep[];
  tokensUsed: number;
  cost: number;
  memoryUsed: {
    snippets: string[];
    numChunks: number;
  };
  finalReport: string;
  nextActions: string[];
}

export interface ProjectWorkspace {
  project_id: string;
  root: string;
  state_path: string;
  manifest_path: string;
}

export interface ProjectManifestFile {
  path: string;
  created_at: string;
  updated_at: string;
  created_by: string;
  last_modified_by: string;
  last_run_id: string;
  file_type: string;
  size_bytes: number;
  summary: string;
}

export interface ProjectRunEntry {
  run_id: string;
  summary: string;
  created_at: string;
}

export interface ProjectManifest {
  project_id: string;
  created_at: string;
  updated_at: string;
  files: ProjectManifestFile[];
  runs: ProjectRunEntry[];
}

export interface ProjectFile {
  path: string;
  file_type: string;
  size_bytes: number;
  summary: string;
  updated_at: string;
}

export interface ProjectChange {
  project_id: string;
  run_id: string;
  path: string;
  operation: string;
  agent_name: string;
  before_summary?: string | null;
  after_summary: string;
  timestamp: string;
}

export interface CommandResult {
  command: string[];
  cwd: string;
  exit_code: number;
  stdout: string;
  stderr: string;
  duration_ms: number;
  allowed: boolean;
  blocked_reason?: string | null;
  executable_command?: string[];
  resolved_cwd?: string | null;
  error_type?: string | null;
  error_message?: string | null;
}

export interface ArtifactRecord {
  id: string;
  run_id: string;
  name: string;
  type: string;
  path: string;
  created_at: string;
  agent_name: string;
  summary: string;
}

export interface CreateRunPayload {
  command: string;
  mode: "mock" | "live";
  project_id?: string | null;
  run_type: "business_launch_plan" | "prototype_build" | "continuation" | "website_update" | "provider_test" | "research_only" | "research";
  allow_file_writes: boolean;
  allow_safe_commands: boolean;
  allow_web_search: boolean;
  allow_ceo_live: boolean;
  use_memory: boolean;
  use_real_coding_agent: boolean;
  allow_live_coding_model_call: boolean;
  real_coding_dry_run: boolean;
  real_coding_model?: string | null;
  real_coding_max_files?: number | null;
  real_coding_max_repair_attempts: number;
  max_cost_usd: number;
  approval_ids?: string[];
}

export interface ApprovalRequest {
  id: string;
  run_id?: string | null;
  project_id?: string | null;
  command: string;
  status: "pending" | "approved" | "rejected" | "expired";
  risk_level: "low" | "medium" | "high" | "critical";
  approval_type: string;
  title: string;
  reason: string;
  requested_action: string;
  estimated_cost_usd?: number | null;
  model?: string | null;
  provider?: string | null;
  created_at: string;
  decided_at?: string | null;
  decision_reason?: string | null;
  metadata: Record<string, unknown>;
}

export interface ApprovalRequiredResponse {
  status: "approval_required";
  run_id: string;
  project_id?: string | null;
  command: string;
  approval_requests: ApprovalRequest[];
}

export interface RunEvent {
  timestamp: string;
  run_id?: string | null;
  agent_name: string;
  agent_role: string;
  status: string;
  action_summary: string;
  input_summary: string;
  output_summary: string;
  model_used: string;
  provider?: string | null;
  estimated_input_tokens: number;
  estimated_output_tokens: number;
  estimated_tokens?: number | null;
  estimated_cost_usd: number;
  artifact_id?: string | null;
}

export interface RunUsageSummary {
  estimated_cost_usd?: number;
  estimated_tokens?: number;
  agents_used?: number;
  models_used?: string[];
  selected_workflow?: string;
  real_coding_agent?: Record<string, any>;
  project_sanity_validation?: Record<string, any>;
  memory_control?: Record<string, any>;
}

export interface PlannedAgent {
  agent_id: string;
  objective: string;
  required_capabilities: string[];
  allowed_tools: string[];
  allowed_files: string[];
  blocked_actions: string[];
  constraints: string[];
  needs_model_selection: boolean;
  selected_model?: Record<string, any> | null;
  selected_search_provider?: Record<string, any> | null;
}

export interface AgentPlan {
  run_goal: string;
  selected_workflow: string;
  selected_agents: PlannedAgent[];
  skipped_agents: Array<{ agent_id: string; reason: string }>;
  safety_constraints: string[];
  blocked_actions: string[];
  memory_requirements: string[];
  approval_required: boolean;
  search_needed: boolean;
  search_unavailable: boolean;
  selected_search_provider?: Record<string, any> | null;
  combined_search_used?: boolean;
  notes: string[];
}

export interface ModelRegistryModel {
  id: string;
  display_name: string;
  provider: string;
  status: string;
  enabled: boolean;
  best_for: string[];
  cost_level: string;
  supports_web_search: boolean;
  supports_vision: boolean;
  supports_tool_use: boolean;
  supports_json: boolean;
  default_agent_roles: string[];
  requires_approval: boolean;
  fallback_models: string[];
  selection_tags: string[];
  known_strengths: string[];
  known_limitations: string[];
  curated_tier?: string;
  auto_selectable?: boolean;
  approved_for_auto_selection?: boolean;
  search_tool_compatible?: boolean;
}

export interface SearchProviderEntry {
  id: string;
  display_name: string;
  provider: string;
  status: string;
  enabled: boolean;
  configured: boolean;
  available: boolean;
  available_for_live: boolean;
  available_in_mock: boolean;
  allow_web_search_global: boolean;
  live_search_available: boolean;
  mock_fixture_available: boolean;
  requires_api_key: boolean;
  requires_approval: boolean;
  default_enabled: boolean;
  blocked_by_default: boolean;
  supports_semantic_search: boolean;
  supports_google_grounding: boolean;
  supports_answer_generation: boolean;
  supports_content_extraction: boolean;
  best_for: string[];
  reasons: string[];
}

export interface SearchToolsStatus {
  providers: SearchProviderEntry[];
  default_provider_id: string;
  allow_web_search_global: boolean;
  notes: string[];
}

export interface SearchLogRecord {
  created_at: string;
  run_id?: string | null;
  project_id?: string | null;
  provider_id?: string | null;
  mode?: "mock" | "live" | string;
  query?: string;
  status?: string;
  source_count?: number;
  sources?: Array<Record<string, any>>;
  cache_hit?: boolean;
  mock_fixture?: boolean;
  error_type?: string | null;
  error_message?: string | null;
  cost?: { estimated_usd?: number; source?: string };
  request_id?: string | null;
}

export interface MemoryItem {
  id: string;
  project_id?: string | null;
  scope: "global" | "project";
  memory_type: string;
  title: string;
  summary: string;
  content: string;
  source_run_id?: string | null;
  tags: string[];
  importance: number;
  token_estimate: number;
  source_urls: string[];
  metadata: Record<string, any>;
}

export interface MemorySearchResult {
  item: MemoryItem;
  score: number;
  why_selected: string[];
}

export interface MemoryStatus {
  enabled: boolean;
  backend_mode: string;
  total_memory_items: number;
  global_memory_items: number;
  projects: Array<{ project_id: string; memory_count: number; last_indexed_at?: string | null; types: Record<string, number> }>;
  index_status: string;
  last_updated_at?: string | null;
  no_secrets: boolean;
}

export interface OpenRouterDiscoverySummary {
  provider: string;
  cached_models_count: number;
  last_synced_at?: string | null;
  promoted_to_curated_registry: boolean;
  sample_model_ids: string[];
  notes: string[];
}

export interface AgentRegistryEntry {
  id: string;
  display_name: string;
  purpose: string;
  allowed_tools: string[];
  allowed_actions: string[];
  blocked_actions: string[];
  default_models: string[];
  preferred_model_tags: string[];
  when_to_use: string[];
  status: string;
}

export interface RunWorkspaceSummary {
  root: string;
  files_created: string[];
  files_edited: string[];
  commands_run: CommandResult[];
  command_success?: boolean | null;
}

export interface RunProjectWorkspaceSummary extends RunWorkspaceSummary {
  project_id: string;
  state_path?: string;
  manifest_path?: string;
}

export interface RunResult {
  run_id: string;
  command: string;
  mode: "mock" | "live";
  project_id?: string | null;
  run_type: string;
  status: string;
  started_at: string;
  completed_at?: string | null;
  events: RunEvent[];
  metrics: {
    total_estimated_tokens: number;
    total_estimated_cost_usd: number;
    agents_used: number;
    tasks_completed: number;
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
  artifacts: ArtifactRecord[];
  workspace?: RunWorkspaceSummary | null;
  project_workspace?: RunProjectWorkspaceSummary | null;
  models_used?: string[];
  project_files_created: string[];
  project_files_updated: string[];
  commands_run: CommandResult[];
  usage_summary: RunUsageSummary;
  memory_updates: string[];
  agent_plan?: AgentPlan | Record<string, unknown>;
  model_selection?: Record<string, any>;
}

export type RunStartResponse = RunResult | ApprovalRequiredResponse;
