import { Search, Table2, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Badge,
  Card,
  Code,
  Confidence,
  EmptyState,
  ErrorNotice,
  SeverityBadge,
  Spinner,
} from "@/components/ui";
import { api } from "@/services/api";
import { useAsync } from "@/hooks/useApi";
import type { TraceabilityRow } from "@/types/api";

const STATUS_TONE: Record<string, "ok" | "critical" | "medium" | "neutral"> = {
  OK: "ok",
  Refined: "ok",
  Critical: "critical",
  "Needs Review": "medium",
};

export function Traceability() {
  const { documentId = "" } = useParams();
  const { data, loading, error, refresh } = useAsync(
    () => api.getTraceability(documentId),
    [documentId],
  );
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<TraceabilityRow | null>(null);

  const rows = useMemo(() => {
    const all = data?.rows ?? [];
    const needle = query.trim().toLowerCase();
    if (!needle) return all;
    return all.filter(
      (row) =>
        row.requirement_code.toLowerCase().includes(needle) ||
        row.original_text.toLowerCase().includes(needle) ||
        row.source.toLowerCase().includes(needle) ||
        row.issues.some((issue) => issue.label.toLowerCase().includes(needle)),
    );
  }, [data, query]);

  if (loading)
    return (
      <div className="flex items-center gap-3 py-20 text-sm text-slate-400">
        <Spinner /> Loading traceability matrix…
      </div>
    );
  if (error) return <ErrorNotice message={error} onRetry={refresh} />;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-sans text-2xl font-bold tracking-tight text-white">Traceability Matrix</h1>
          <p className="mt-1 text-xs text-slate-400">
            Every requirement mapped back to source location, page, and cited findings.
          </p>
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-slate-500" aria-hidden />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search requirements, findings or section..."
            aria-label="Search the matrix"
            className="h-10 w-80 rounded-xl border border-white/15 bg-[#070e1b] pl-10 pr-3.5 text-xs text-white placeholder-slate-500 focus:border-sky-400 focus:outline-none"
          />
        </div>
      </div>

      {rows.length === 0 ? (
        <EmptyState icon={<Table2 className="size-6 text-emerald-400" />} title="No matching requirements found" />
      ) : (
        <Card className="overflow-hidden border-white/10 bg-[#070e1b]/70 backdrop-blur-xl">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-left text-xs">
              <thead className="border-b border-white/10 bg-white/[0.04] text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                <tr>
                  <th className="px-5 py-3.5">ID</th>
                  <th className="px-5 py-3.5">Requirement Statement</th>
                  <th className="px-5 py-3.5">Source</th>
                  <th className="px-5 py-3.5">Detected Findings</th>
                  <th className="px-5 py-3.5">Refinement Status</th>
                  <th className="px-5 py-3.5">Verdict</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {rows.map((row) => (
                  <tr
                    key={row.requirement_id}
                    onClick={() => setSelected(row)}
                    className="cursor-pointer align-top transition-colors hover:bg-white/[0.04]"
                  >
                    <td className="px-5 py-3.5">
                      <Code>{row.requirement_code}</Code>
                    </td>
                    <td className="max-w-md px-5 py-3.5">
                      <p className="line-clamp-2 text-slate-200">{row.original_text}</p>
                    </td>
                    <td className="px-5 py-3.5 font-mono text-[11px] text-slate-400">{row.source}</td>
                    <td className="px-5 py-3.5">
                      <div className="flex flex-wrap gap-1">
                        {row.issues.length === 0 ? (
                          <span className="text-[11px] text-emerald-400/80">Clean (0 defects)</span>
                        ) : (
                          row.issues.map((issue) => (
                            <Badge key={issue.id} tone={issue.severity}>
                              {issue.label}
                            </Badge>
                          ))
                        )}
                      </div>
                    </td>
                    <td className="max-w-xs px-5 py-3.5">
                      <p className="line-clamp-2 text-[11px] text-slate-400">
                        {row.suggested_refinement ?? "—"}
                      </p>
                    </td>
                    <td className="px-5 py-3.5">
                      <Badge tone={STATUS_TONE[row.status] ?? "neutral"}>{row.status}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Slide-over Inspection Drawer */}
      {selected ? (
        <div
          className="fixed inset-0 z-40 flex justify-end bg-black/60 backdrop-blur-sm transition-opacity"
          onClick={() => setSelected(null)}
          role="presentation"
        >
          <aside
            className="h-full w-full max-w-lg overflow-y-auto border-l border-white/15 bg-[#070e1b]/95 p-6 shadow-2xl backdrop-blur-2xl"
            onClick={(event) => event.stopPropagation()}
            aria-label={`Details for ${selected.requirement_code}`}
          >
            <div className="flex items-center justify-between border-b border-white/10 pb-4">
              <div className="flex items-center gap-2">
                <Code>{selected.requirement_code}</Code>
                <Badge tone={STATUS_TONE[selected.status] ?? "neutral"}>{selected.status}</Badge>
              </div>
              <button
                onClick={() => setSelected(null)}
                aria-label="Close details"
                className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-white/10 hover:text-white"
              >
                <X className="size-4" aria-hidden />
              </button>
            </div>

            <div className="space-y-5 pt-5">
              <div>
                <p className="font-mono text-[10px] uppercase tracking-wider text-slate-500">Original Requirement Text</p>
                <p className="mt-1 text-xs leading-relaxed text-white">{selected.original_text}</p>
              </div>
              <div>
                <p className="font-mono text-[10px] uppercase tracking-wider text-slate-500">Document Trace Location</p>
                <p className="mt-1 font-mono text-xs text-slate-300">{selected.source}</p>
              </div>

              <div>
                <p className="font-mono text-[10px] uppercase tracking-wider text-slate-500">
                  Detected Findings ({selected.issues.length})
                </p>
                <div className="mt-2 space-y-3">
                  {selected.issues.length === 0 ? (
                    <p className="text-xs text-emerald-400">No issues flagged against this requirement.</p>
                  ) : (
                    selected.issues.map((issue) => (
                      <div key={issue.id} className="rounded-xl border border-white/10 bg-white/[0.02] p-3.5">
                        <div className="flex items-center gap-2">
                          <Badge tone={issue.severity}>{issue.label}</Badge>
                          <SeverityBadge severity={issue.severity} />
                          <div className="ml-auto">
                            <Confidence value={issue.confidence} />
                          </div>
                        </div>
                        {issue.evidence ? (
                          <p className="mt-2 font-mono text-xs text-amber-200 bg-amber-500/10 p-2 rounded-lg border border-amber-500/20">
                            “{issue.evidence}”
                          </p>
                        ) : null}
                        {issue.description ? (
                          <p className="mt-1.5 text-xs text-slate-300">{issue.description}</p>
                        ) : null}
                      </div>
                    ))
                  )}
                </div>
              </div>

              {selected.suggested_refinement ? (
                <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-4">
                  <p className="font-mono text-[10px] uppercase tracking-wider text-emerald-400">
                    Suggested Refinement
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-emerald-100">
                    {selected.suggested_refinement}
                  </p>
                </div>
              ) : null}
            </div>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
