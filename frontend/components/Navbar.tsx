import { Activity, Cpu, Plus, Server } from "lucide-react";

type NavbarProps = {
  ceoModel: string;
  workerModel: string;
  backendOnline: boolean;
  runTitle: string;
};

export function Navbar({ ceoModel, workerModel, backendOnline, runTitle }: NavbarProps) {
  return (
    <header className="sticky top-0 z-20 border-b border-hive-border bg-hive-bg/88 backdrop-blur">
      <div className="flex flex-col gap-4 px-5 py-4 md:flex-row md:items-center md:justify-between lg:px-8">
        <div className="min-w-0">
          <p className="fine-label">Current workspace</p>
          <h1 className="mt-1 truncate text-lg font-semibold text-hive-text md:text-xl">{runTitle}</h1>
          <p className="mt-1 text-sm text-hive-muted">
            Plan work, assign agents, retrieve memory, and review practical execution logs.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-hive-muted">
          <span className="inline-flex items-center gap-2 rounded-lg border border-hive-border bg-hive-panel px-3 py-2">
            <Server className={backendOnline ? "h-3.5 w-3.5 text-hive-green" : "h-3.5 w-3.5 text-hive-warning"} />
            Backend {backendOnline ? "online" : "offline"}
          </span>
          <span className="inline-flex items-center gap-2 rounded-lg border border-hive-border bg-hive-panel px-3 py-2">
            <Activity className="h-3.5 w-3.5 text-hive-amber" />
            CEO: {ceoModel}
          </span>
          <span className="inline-flex items-center gap-2 rounded-lg border border-hive-border bg-hive-panel px-3 py-2">
            <Cpu className="h-3.5 w-3.5 text-hive-cyan" />
            Worker: {workerModel}
          </span>
          <a
            href="#command"
            className="inline-flex items-center gap-2 rounded-lg bg-hive-text px-3 py-2 text-xs font-semibold text-hive-bg transition hover:bg-white"
          >
            <Plus className="h-3.5 w-3.5" />
            New Run
          </a>
        </div>
      </div>
    </header>
  );
}
