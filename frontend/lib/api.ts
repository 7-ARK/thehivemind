const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type AgentInfo = {
  name: string;
  role: string;
  assigned_model: string;
  status: string;
  latest_action: string;
  completed_work: string[];
};

export type RunEvent = {
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

export type MemorySnippet = {
  title: string;
  content: string;
  relevance_score: number;
};

export type MemorySummary = {
  core_memory: string;
  current_state: string;
  retrieved_snippets: MemorySnippet[];
  vector_store_path: string;
};

export type TaskNode = {
  id: string;
  label: string;
  status: string;
};

export type TaskEdge = {
  source: string;
  target: string;
};

export type TaskGraph = {
  nodes: TaskNode[];
  edges: TaskEdge[];
};

export type RunRecord = {
  run_id: string;
  command: string;
  mode: "mock" | "live";
  status: string;
  started_at: string;
  completed_at: string | null;
  events: RunEvent[];
  agents: AgentInfo[];
  task_graph: TaskGraph;
  metrics: {
    total_estimated_tokens: number;
    total_estimated_cost_usd: number;
    agents_used: number;
    tasks_completed: number;
    run_duration_seconds: number;
    memory_chunks_retrieved: number;
  };
  memory: MemorySummary;
  final_output: {
    summary: string;
    what_was_done: string[];
    recommended_next_actions: string[];
    generated_artifacts: string[];
  };
};

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export function startRun(command: string) {
  return request<RunRecord>("/api/runs", {
    method: "POST",
    body: JSON.stringify({ command, mode: "mock" })
  });
}

export function getAgents() {
  return request<AgentInfo[]>("/api/agents");
}

export function getMemorySummary() {
  return request<MemorySummary>("/api/memory/summary");
}
