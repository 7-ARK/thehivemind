import { BarChart3, Brain, Command, Hexagon, History, Settings, Users } from "lucide-react";

type SidebarProps = {
  backendOnline: boolean;
};

const navItems = [
  { label: "Command Center", href: "#command", icon: Command },
  { label: "Runs", href: "#timeline", icon: History },
  { label: "Agents", href: "#agents", icon: Users },
  { label: "Memory", href: "#memory", icon: Brain },
  { label: "Metrics", href: "#metrics", icon: BarChart3 },
  { label: "Settings", href: "#settings", icon: Settings }
];

export function Sidebar({ backendOnline }: SidebarProps) {
  return (
    <aside className="border-hive-border bg-hive-shell px-4 py-5 lg:fixed lg:inset-y-0 lg:left-0 lg:w-64 lg:border-r">
      <div className="flex h-full flex-col">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-lg border border-hive-border bg-hive-panel">
            <Hexagon className="h-5 w-5 text-hive-amber" />
          </div>
          <div>
            <div className="text-sm font-semibold text-hive-text">TheHiveMind</div>
            <div className="text-xs text-hive-muted">Agent operations</div>
          </div>
        </div>

        <nav className="mt-8 grid gap-1">
          {navItems.map(({ label, href, icon: Icon }) => (
            <a
              key={label}
              href={href}
              className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-hive-muted transition hover:bg-hive-panel hover:text-hive-text"
            >
              <Icon className="h-4 w-4" />
              {label}
            </a>
          ))}
        </nav>

        <div className="mt-5 rounded-lg border border-hive-border bg-hive-panel p-3 lg:mt-auto">
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs font-medium text-hive-text">Mock Mode</span>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-hive-border bg-hive-panelSoft px-2 py-1 text-[11px] text-hive-muted">
              <span className={backendOnline ? "status-dot" : "h-2 w-2 rounded-full bg-hive-warning"} />
              {backendOnline ? "online" : "offline"}
            </span>
          </div>
          <p className="mt-2 text-xs leading-5 text-hive-muted">
            Local orchestration is visible without spending provider tokens.
          </p>
        </div>
      </div>
    </aside>
  );
}

