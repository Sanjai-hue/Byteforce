import {
  AlertTriangle,
  Copy,
  GitBranch,
  HelpCircle,
  LayoutDashboard,
  ListChecks,
  ShieldAlert,
  Table2,
  UploadCloud,
  ChevronRight,
  Sparkles,
} from "lucide-react";
import { NavLink, Outlet, useParams, Link } from "react-router-dom";
import { api } from "@/services/api";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui";
import { useAsync } from "@/hooks/useApi";

const NAV = [
  { to: "", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "requirements", label: "Clean requirements", icon: ListChecks },
  { to: "ambiguities", label: "Ambiguities", icon: AlertTriangle },
  { to: "contradictions", label: "Contradictions", icon: ShieldAlert },
  { to: "duplicates", label: "Duplicates", icon: Copy },
  { to: "missing-information", label: "Missing information", icon: HelpCircle },
  { to: "dependencies", label: "Dependency graph", icon: GitBranch },
  { to: "traceability", label: "Traceability matrix", icon: Table2 },
];

export function DashboardLayout() {
  const { documentId = "" } = useParams();
  const { data } = useAsync(() => api.getStatus(documentId), [documentId]);

  return (
    <div className="min-h-screen bg-[#02060f] text-white selection:bg-sky-500/30">
      {/* Top Ambient Glow Line */}
      <div className="fixed top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-sky-400/30 to-transparent z-30" />

      {/* Header */}
      <header className="sticky top-0 z-20 border-b border-white/10 bg-[#070e1b]/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1440px] items-center gap-4 px-6">
          {/* Logo & Brand */}
          <Link to="/" className="flex items-center gap-2.5 transition-opacity hover:opacity-85">
            <svg className="h-4.5 w-6 fill-white" viewBox="0 0 23 17" aria-hidden="true">
              <path d="M8.15 0.9 L4.55 0.9 L0.5 9.3 L4.1 9.3 Z" />
              <path d="M17.0 0 L13.4 0 L6.15 16.4 L9.75 16.4 Z" />
              <path d="M22.9 0 L19.3 0 L15.0 7.6 L18.6 7.6 Z" />
              <path d="M22.6 6.9 L19.0 6.9 L14.05 16.4 L17.65 16.4 Z" />
            </svg>
            <span className="font-sans text-sm font-bold tracking-[0.12em] text-white">
              ReqGuard <span className="text-sky-400">AI</span>
            </span>
          </Link>

          <ChevronRight className="size-4 text-white/20" />
          <span className="truncate text-xs font-medium text-slate-400">
            Specification Analysis
          </span>

          {/* Right Header Badges & Actions */}
          <div className="ml-auto flex items-center gap-3">
            {data?.status === "completed" ? (
              <Badge tone="ok">Analysis complete</Badge>
            ) : data?.status === "failed" ? (
              <Badge tone="critical">Analysis failed</Badge>
            ) : data ? (
              <Badge tone="brand">
                <Sparkles className="size-3 mr-1" />
                {data.stage_label}
              </Badge>
            ) : null}

            {data?.stats?.llm_model ? (
              <span className="hidden font-mono text-[11px] text-slate-500 md:inline bg-white/[0.04] px-2 py-0.5 rounded border border-white/5">
                {data.stats.llm_model}
              </span>
            ) : null}

            <Link
              to="/upload"
              className="flex items-center gap-1.5 rounded-full border border-white/20 bg-white/[0.05] px-3 py-1.5 text-xs font-medium text-white transition-all hover:border-white/40 hover:bg-white/10 active:scale-[0.98]"
            >
              <UploadCloud className="size-3.5 text-sky-400" />
              <span>New Upload</span>
            </Link>
          </div>
        </div>
      </header>

      {/* Body / Dashboard Content */}
      <div className="mx-auto flex max-w-[1440px] gap-6 px-6 py-6">
        {/* Sidebar Nav */}
        <aside aria-label="Reports" className="hidden w-64 shrink-0 lg:block">
          <div className="sticky top-24 rounded-2xl border border-white/10 bg-[#070e1b]/70 p-2.5 backdrop-blur-xl shadow-xl">
            <div className="px-3 py-2 text-[10px] font-semibold tracking-wider text-slate-400 uppercase">
              Analysis Reports
            </div>
            <ul className="space-y-1 mt-1">
              {NAV.map(({ to, label, icon: Icon, end }) => (
                <li key={label}>
                  <NavLink
                    to={to ? `/dashboard/${documentId}/${to}` : `/dashboard/${documentId}`}
                    end={end}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-2.5 rounded-xl px-3 py-2 text-xs font-medium transition-all duration-150",
                        isActive
                          ? "bg-gradient-to-r from-sky-500/20 via-sky-500/10 to-transparent text-white border border-sky-400/40 shadow-[0_0_16px_rgba(56,189,248,0.15)]"
                          : "text-slate-400 hover:bg-white/[0.06] hover:text-white",
                      )
                    }
                  >
                    <Icon className="size-4 shrink-0 text-sky-400/80" aria-hidden />
                    {label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        </aside>

        {/* Main Content Area */}
        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
