import { useState } from "react";
import { NavLink, Outlet } from "react-router";
import {
  FileDiff,
  FolderKanban,
  GitBranch,
  LayoutDashboard,
  Menu,
  Pencil,
  ScrollText,
  Settings,
  Share2,
  Upload,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { HealthProvider } from "../lib/healthContext";
import { HealthIndicator } from "./HealthIndicator";

type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
};

const workItems: NavItem[] = [
  { to: "/app", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/app/new", label: "New project", icon: Upload },
  { to: "/app/results", label: "Results", icon: FolderKanban },
  { to: "/app/reports", label: "Reports", icon: ScrollText },
  { to: "/app/edit", label: "Edit", icon: Pencil },
  { to: "/app/versions", label: "Versions", icon: GitBranch },
  { to: "/app/export", label: "Export", icon: Share2 },
];

const otherItems: NavItem[] = [
  { to: "/", label: "Home", icon: FileDiff, end: true },
  { to: "/app/settings", label: "Settings", icon: Settings },
];

function NavList({ items, onNavigate }: { items: NavItem[]; onNavigate: () => void }) {
  return (
    <ul className="space-y-1">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.end}
              onClick={onNavigate}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-control px-3 py-2 text-sm font-semibold ${
                  isActive ? "bg-white/10 text-nav-text" : "text-nav-muted hover:bg-white/5 hover:text-nav-text"
                }`
              }
            >
              <Icon size={18} aria-hidden="true" />
              {item.label}
            </NavLink>
          </li>
        );
      })}
    </ul>
  );
}

function ShellFrame() {
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = () => setMenuOpen(false);

  const sidebar = (
    <div className="flex h-full flex-col">
      <p className="px-3 pb-2 font-mono text-[11px] uppercase tracking-[0.2em] text-nav-muted">Work</p>
      <NavList items={workItems} onNavigate={closeMenu} />
      <p className="mt-6 px-3 pb-2 font-mono text-[11px] uppercase tracking-[0.2em] text-nav-muted">App</p>
      <NavList items={otherItems} onNavigate={closeMenu} />
    </div>
  );

  return (
    <div className="min-h-screen bg-paper text-ink">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:bg-paper-raised focus:px-3 focus:py-2">
        Skip to content
      </a>
      <header className="sticky top-0 z-30 flex min-h-header items-center justify-between gap-3 border-b border-line bg-paper/95 px-4 py-2 backdrop-blur md:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            className="inline-flex h-10 w-10 items-center justify-center rounded-control border border-line lg:hidden"
            aria-expanded={menuOpen}
            aria-controls="app-sidebar"
            onClick={() => setMenuOpen((open) => !open)}
          >
            {menuOpen ? <X size={18} aria-hidden="true" /> : <Menu size={18} aria-hidden="true" />}
            <span className="sr-only">{menuOpen ? "Close menu" : "Open menu"}</span>
          </button>
          <div>
            <p className="font-display text-xl leading-none tracking-tight">UNTANGLE</p>
            <p className="hidden font-mono text-[10px] uppercase tracking-[0.18em] text-ink-soft sm:block">P&amp;ID simplification</p>
          </div>
        </div>
        <HealthIndicator />
      </header>
      <div className="lg:grid lg:grid-cols-[17rem_minmax(0,1fr)]">
        <aside id="app-sidebar" className="hidden bg-nav px-3 py-6 lg:block lg:min-h-[calc(100vh-4.25rem)]">
          {sidebar}
        </aside>
        {menuOpen ? (
          <div className="fixed inset-x-0 bottom-0 top-header z-20 bg-nav px-4 py-6 lg:hidden">
            {sidebar}
          </div>
        ) : null}
        <main id="main" className="px-4 py-8 md:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export function AppShell() {
  return (
    <HealthProvider>
      <ShellFrame />
    </HealthProvider>
  );
}
