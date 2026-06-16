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
