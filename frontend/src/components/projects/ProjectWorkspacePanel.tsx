import { useEffect, useMemo, useState } from "react";
import {
  getProject,
  getProjectChanges,
  getProjectFile,
  getProjectFiles,
  getProjectManifest,
  getProjectRuns,
  getProjectState,
  getRunArtifacts,
  getRunCommands,
} from "../../lib/api";
import { ArtifactRecord, CommandResult, ProjectChange, ProjectFile, ProjectManifest, ProjectRunEntry } from "../../types";
import ProjectArtifactList from "./ProjectArtifactList";
import ProjectChangeLog from "./ProjectChangeLog";
import ProjectCommandLog from "./ProjectCommandLog";
import ProjectFilePreview from "./ProjectFilePreview";
import ProjectFileTree from "./ProjectFileTree";
import ProjectManifestTable from "./ProjectManifestTable";
import ProjectRunHistory from "./ProjectRunHistory";
import ProjectStateCard from "./ProjectStateCard";

export default function ProjectWorkspacePanel() {
  const [projectId, setProjectId] = useState("greek-yogurt-test");
  const [loadedProjectId, setLoadedProjectId] = useState("greek-yogurt-test");
  const [stateContent, setStateContent] = useState("");
  const [manifest, setManifest] = useState<ProjectManifest | null>(null);
  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [runs, setRuns] = useState<ProjectRunEntry[]>([]);
  const [changes, setChanges] = useState<ProjectChange[]>([]);
  const [commands, setCommands] = useState<CommandResult[]>([]);
  const [artifacts, setArtifacts] = useState<ArtifactRecord[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | undefined>();
  const [selectedRunId, setSelectedRunId] = useState<string | undefined>();
  const [fileContent, setFileContent] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [backendError, setBackendError] = useState<string | null>(null);

  const latestRun = useMemo(() => runs[runs.length - 1], [runs]);

  async function loadProject(id: string) {
    setLoading(true);
    setBackendError(null);
    try {
      await getProject(id);
      const [state, manifestPayload, filesPayload, runsPayload, changesPayload] = await Promise.all([
        getProjectState(id),
        getProjectManifest(id),
        getProjectFiles(id),
        getProjectRuns(id),
        getProjectChanges(id),
      ]);
      setStateContent(state.content);
      setManifest(manifestPayload);
      setFiles(filesPayload);
      setRuns(runsPayload.runs);
      setChanges(changesPayload.changes);
      const nextRunId = runsPayload.runs[runsPayload.runs.length - 1]?.run_id;
      setSelectedRunId(nextRunId);
      setSelectedPath(filesPayload[0]?.path);
      setLoadedProjectId(id);
    } catch (error: any) {
      setBackendError(error.message || "Backend offline or project unavailable.");
      setStateContent("");
      setManifest(null);
      setFiles([]);
      setRuns([]);
      setChanges([]);
      setCommands([]);
      setArtifacts([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadProject(loadedProjectId);
  }, []);

  useEffect(() => {
    if (!selectedPath) {
      setFileContent("");
      return;
    }
    setFileError(null);
    getProjectFile(loadedProjectId, selectedPath)
      .then((file) => setFileContent(file.content))
      .catch((error) => {
        setFileContent("");
        setFileError(error.message || "Could not load file.");
      });
  }, [loadedProjectId, selectedPath]);

  useEffect(() => {
    const runId = selectedRunId || latestRun?.run_id;
    if (!runId) {
      setCommands([]);
      setArtifacts([]);
      return;
    }
    Promise.all([getRunCommands(runId), getRunArtifacts(runId)])
      .then(([commandPayload, artifactPayload]) => {
        setCommands(commandPayload);
        setArtifacts(artifactPayload);
      })
      .catch(() => {
        setCommands([]);
        setArtifacts([]);
      });
  }, [selectedRunId, latestRun]);

  return (
    <div className="space-y-6">
      <div className="border-b border-[#2c2e33] pb-5">
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-[#e9ecef]">Project Workspace</h1>
            <p className="text-xs text-[#909296] mt-1">
              Inspect persistent project files, state, run history, changes, commands, and artifacts.
            </p>
          </div>
          <div className="flex gap-2">
            <input
              value={projectId}
              onChange={(event) => setProjectId(event.target.value)}
              className="bg-[#141517] border border-[#2c2e33] rounded text-[#e9ecef] text-xs px-3 py-2 outline-none focus:ring-1 focus:ring-[#20c997]/60 min-w-64"
              placeholder="project_id"
            />
            <button
              onClick={() => loadProject(projectId)}
              className="bg-[#20c997] text-[#141517] px-3 py-2 rounded text-xs font-bold"
            >
              Load
            </button>
          </div>
        </div>
      </div>

      {backendError && (
        <div className="bg-[#fab005]/10 border border-[#fab005]/30 text-[#fab005] rounded-lg p-4 text-xs">
          {backendError} Backend URL: http://127.0.0.1:8000
        </div>
      )}

      <ProjectStateCard content={stateContent} loading={loading} />

      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">
        <ProjectFileTree files={files} selectedPath={selectedPath} onSelect={setSelectedPath} />
        <ProjectFilePreview path={selectedPath} content={fileContent} error={fileError} />
      </div>

      <ProjectManifestTable files={manifest?.files ?? []} />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <ProjectRunHistory runs={runs} selectedRunId={selectedRunId} onSelect={setSelectedRunId} />
        <ProjectChangeLog changes={changes} />
        <ProjectCommandLog commands={commands} />
        <ProjectArtifactList artifacts={artifacts} />
      </div>
    </div>
  );
}
