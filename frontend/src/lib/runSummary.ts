import { ArtifactRecord, CommandResult, ProjectChange, RunResult } from "../types";

export interface FileSummaryItem {
  path: string;
  operation: "created" | "updated";
  agentName?: string;
  summary?: string;
}

export function collectRunFiles(run: RunResult, changes: ProjectChange[] = []): { created: FileSummaryItem[]; updated: FileSummaryItem[] } {
  const created = new Map<string, FileSummaryItem>();
  const updated = new Map<string, FileSummaryItem>();

  addPathList(created, run.project_files_created, "created");
  addPathList(updated, run.project_files_updated, "updated");
  addPathList(created, run.workspace?.files_created ?? [], "created");
  addPathList(updated, run.workspace?.files_edited ?? [], "updated");
  addPathList(created, run.project_workspace?.files_created ?? [], "created");
  addPathList(updated, run.project_workspace?.files_edited ?? [], "updated");

  for (const artifact of run.artifacts ?? []) {
    if (artifact.type === "project_file") {
      const existing = updated.get(artifact.name) ?? created.get(artifact.name);
      const item = {
        path: artifact.name,
        operation: existing?.operation ?? "updated",
        agentName: artifact.agent_name,
        summary: artifact.summary,
      } satisfies FileSummaryItem;
      if (item.operation === "created") created.set(item.path, item);
      else updated.set(item.path, item);
    }
  }

  for (const change of changes.filter((item) => item.run_id === run.run_id)) {
    const item = {
      path: change.path,
      operation: change.operation === "created" ? "created" : "updated",
      agentName: change.agent_name,
      summary: change.after_summary,
    } satisfies FileSummaryItem;
    if (item.operation === "created") created.set(item.path, item);
    else updated.set(item.path, item);
  }

  return { created: Array.from(created.values()), updated: Array.from(updated.values()) };
}

export function collectRunCommands(run: RunResult, endpointCommands: CommandResult[] = []): CommandResult[] {
  if (run.commands_run?.length) return run.commands_run;
  if (run.workspace?.commands_run?.length) return run.workspace.commands_run;
  if (run.project_workspace?.commands_run?.length) return run.project_workspace.commands_run;
  if (endpointCommands.length) return endpointCommands;
  return [];
}

export function mergeArtifacts(runArtifacts: ArtifactRecord[], endpointArtifacts: ArtifactRecord[]): ArtifactRecord[] {
  const byId = new Map<string, ArtifactRecord>();
  for (const artifact of [...runArtifacts, ...endpointArtifacts]) {
    byId.set(artifact.id, artifact);
  }
  return Array.from(byId.values());
}

function addPathList(target: Map<string, FileSummaryItem>, paths: string[], operation: "created" | "updated") {
  for (const path of paths) {
    if (path && !target.has(path)) {
      target.set(path, { path, operation });
    }
  }
}
