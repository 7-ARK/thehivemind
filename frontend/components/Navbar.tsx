import { Activity, Cpu, Hexagon } from "lucide-react";

type NavbarProps = {
  ceoModel: string;
  workerModel: string;
};

export function Navbar({ ceoModel, workerModel }: NavbarProps) {
  return (
    <header className="sticky top-0 z-20 border-b border-hive-border bg-hive-bg/86 backdrop-blur">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-4 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-md border border-hive-border bg-hive-panelSoft">
            <Hexagon className="h-5 w-5 text-hive-accent" />
          </div>
          <div>
            <div className="text-lg font-semibold tracking-normal">TheHiveMind</div>
            <p className="text-sm text-hive-muted">
              Multi-agent AI operating system for planning, delegation, memory, and execution.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-hive-muted">
          <span className="inline-flex items-center gap-2 rounded-md border border-hive-border bg-hive-panelSoft px-3 py-2">
            <span className="status-dot" />
            Mock Mode
          </span>
          <span className="inline-flex items-center gap-2 rounded-md border border-hive-border bg-hive-panelSoft px-3 py-2">
            <Activity className="h-3.5 w-3.5 text-hive-accent" />
            CEO: {ceoModel}
          </span>
          <span className="inline-flex items-center gap-2 rounded-md border border-hive-border bg-hive-panelSoft px-3 py-2">
            <Cpu className="h-3.5 w-3.5 text-hive-teal" />
            Worker: {workerModel}
          </span>
        </div>
      </div>
    </header>
  );
}

