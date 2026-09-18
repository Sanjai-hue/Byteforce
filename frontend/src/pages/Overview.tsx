import {
  AlertTriangle,
  Copy,
  GitBranch,
  HelpCircle,
  ListChecks,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { Card, CardBody, ErrorNotice, ProgressBar, Spinner } from "@/components/ui";
import { api } from "@/services/api";
import { useAsync } from "@/hooks/useApi";

const CARDS = [
  { key: "requirements", label: "Requirements", icon: ListChecks, to: "requirements", tone: "text-sky-400", glow: "hover:border-sky-400/40" },
  { key: "ambiguities", label: "Ambiguities", icon: AlertTriangle, to: "ambiguities", tone: "text-amber-400", glow: "hover:border-amber-400/40" },
  { key: "contradictions", label: "Contradictions", icon: ShieldAlert, to: "contradictions", tone: "text-red-400", glow: "hover:border-red-400/40" },
  { key: "duplicates", label: "Duplicates", icon: Copy, to: "duplicates", tone: "text-yellow-400", glow: "hover:border-yellow-400/40" },
  { key: "dependencies", label: "Dependencies", icon: GitBranch, to: "dependencies", tone: "text-indigo-400", glow: "hover:border-indigo-400/40" },
  { key: "missing_information", label: "Missing information", icon: HelpCircle, to: "missing-information", tone: "text-slate-400", glow: "hover:border-slate-400/40" },
] as const;

export function Overview() {
  const { documentId = "" } = useParams();
  const { data, loading, error, refresh } = useAsync(() => api.getStatus(documentId), [documentId]);

  if (loading) {
    return (
      <div className="flex items-center gap-3 py-20 text-sm text-slate-400">
        <Spinner /> Loading intelligence metrics…
      </div>
    );
  }
  if (error) return <ErrorNotice message={error} onRetry={refresh} />;
  if (!data) return null;

  const stats = data.stats ?? {};

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-400/30 bg-sky-500/10 px-2.5 py-0.5 text-[11px] font-medium text-sky-300">
            <Sparkles className="size-3" />
            Active Session
          </span>
        </div>
        <h1 className="mt-2 font-sans text-2xl font-bold tracking-tight text-white">Analysis Overview</h1>
        <p className="mt-1 text-xs text-slate-400">
          Every metric below is ground-traced from this run. Open any category to inspect evidence.
        </p>
      </div>

      {data.status !== "completed" ? (
        <Card className="border-sky-400/30 bg-[#070e1b]/80 shadow-[0_0_24px_rgba(56,189,248,0.1)]">
          <CardBody>
            <div className="flex items-center gap-3">
              {data.status === "failed" ? null : <Spinner className="border-sky-400/30 border-t-sky-400" />}
              <p className="flex-1 font-sans text-sm font-semibold text-white">{data.stage_label}</p>
              <span className="font-mono text-sm font-bold text-sky-400">{data.progress}%</span>
            </div>
            <div className="mt-3">
              <ProgressBar value={data.progress} />
            </div>
            {data.error_message ? (
              <p className="mt-3 text-xs text-red-300">{data.error_message}</p>
            ) : null}
          </CardBody>
        </Card>
      ) : null}

      {/* Metric Cards Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {CARDS.map(({ key, label, icon: Icon, to, tone, glow }) => {
          const value = stats[key as keyof typeof stats];
          return (
            <Link key={key} to={`/dashboard/${documentId}/${to}`} className="group">
              <Card className={`h-full border border-white/10 bg-[#070e1b]/60 backdrop-blur-xl transition-all duration-200 group-hover:scale-[1.01] ${glow}`}>
                <CardBody className="p-5">
                  <div className="flex items-start justify-between">
                    <span className="text-xs font-medium text-slate-400 group-hover:text-slate-200">{label}</span>
                    <div className="flex size-8 items-center justify-center rounded-lg bg-white/[0.04] border border-white/5">
                      <Icon className={`size-4.5 ${tone}`} aria-hidden />
                    </div>
                  </div>
                  <p className="mt-3 font-sans text-3xl font-bold tabular-nums text-white">
                    {typeof value === "number" ? value : "—"}
                  </p>
                  <div className="mt-2 text-[11px] text-slate-500 group-hover:text-sky-400/80 transition-colors">
                    Click to view cited report &rarr;
                  </div>
                </CardBody>
              </Card>
            </Link>
          );
        })}
      </div>

      {/* System Run Diagnostics Card */}
      <Card className="border border-white/10 bg-[#070e1b]/50 backdrop-blur-xl">
        <CardBody className="grid gap-4 text-xs sm:grid-cols-3 p-5">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-wider text-slate-500">Pipeline State</p>
            <p className="mt-1 font-sans text-sm font-semibold text-emerald-400">{data.stage_label}</p>
          </div>
          <div>
            <p className="font-mono text-[10px] uppercase tracking-wider text-slate-500">Reasoning Core</p>
            <p className="mt-1 font-mono text-xs text-slate-300">{stats.llm_model ?? "llama-3.3-70b-versatile"}</p>
          </div>
          <div>
            <p className="font-mono text-[10px] uppercase tracking-wider text-slate-500">Vector Embeddings</p>
            <p className="mt-1 font-mono text-xs text-slate-300">{stats.embedding_model ?? "BAAI/bge-small-en-v1.5 (384d)"}</p>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
