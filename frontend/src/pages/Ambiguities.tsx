import { AlertTriangle, Check, Pencil, X } from "lucide-react";
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  CardBody,
  Code,
  Confidence,
  EmptyState,
  ErrorNotice,
  SeverityBadge,
  Spinner,
} from "@/components/ui";
import { api } from "@/services/api";
import { useAsync } from "@/hooks/useApi";
import type { AmbiguityFinding, Severity } from "@/types/api";

const SEVERITY_ORDER: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3 };

export function Ambiguities() {
  const { documentId = "" } = useParams();
  const { data, loading, error, refresh } = useAsync(
    () => api.getAmbiguities(documentId),
    [documentId],
  );
  const [severity, setSeverity] = useState<Severity | "all">("all");
  const [sort, setSort] = useState<"severity" | "confidence">("severity");

  const findings = useMemo(() => {
    const rows = data?.ambiguities ?? [];
    const filtered = severity === "all" ? rows : rows.filter((row) => row.severity === severity);
    return [...filtered].sort((a, b) =>
      sort === "severity"
        ? SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]
        : b.confidence - a.confidence,
    );
  }, [data, severity, sort]);

  if (loading) {
    return (
      <div className="flex items-center gap-3 py-20 text-sm text-slate-400">
        <Spinner /> Loading ambiguity intelligence…
      </div>
    );
  }
  if (error) return <ErrorNotice message={error} onRetry={refresh} />;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-sans text-2xl font-bold tracking-tight text-white">Ambiguity Report</h1>
          <p className="mt-1 text-xs text-slate-400">
            Requirements with untestable, subjective adjectives or vague performance boundaries.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={severity}
            onChange={(event) => setSeverity(event.target.value as Severity | "all")}
            aria-label="Filter by severity"
            className="h-9 rounded-xl border border-white/15 bg-[#070e1b] px-3 text-xs text-white focus:border-sky-400 focus:outline-none"
          >
            <option value="all">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <select
            value={sort}
            onChange={(event) => setSort(event.target.value as "severity" | "confidence")}
            aria-label="Sort findings"
            className="h-9 rounded-xl border border-white/15 bg-[#070e1b] px-3 text-xs text-white focus:border-sky-400 focus:outline-none"
          >
            <option value="severity">Sort by Severity</option>
            <option value="confidence">Sort by Confidence</option>
          </select>
        </div>
      </div>

      {findings.length === 0 ? (
        <EmptyState
          icon={<AlertTriangle className="size-6 text-emerald-400" />}
          title="No ambiguities reported"
          description="Every statement in this specification contains verifiable, testable criteria."
        />
      ) : (
        <div className="space-y-4">
          {findings.map((finding) => (
            <AmbiguityCard key={finding.issue_id} finding={finding} onChanged={refresh} />
          ))}
        </div>
      )}
    </div>
  );
}

function AmbiguityCard({
  finding,
  onChanged,
}: {
  finding: AmbiguityFinding;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(finding.suggested_refinement ?? "");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const act = async (action: "accept" | "reject" | "edit") => {
    if (!finding.refinement_id) return;
    setBusy(true);
    setActionError(null);
    try {
      if (action === "accept") await api.acceptRefinement(finding.refinement_id);
      if (action === "reject") await api.rejectRefinement(finding.refinement_id);
      if (action === "edit") await api.editRefinement(finding.refinement_id, draft);
      setEditing(false);
      onChanged();
    } catch {
      setActionError("That action could not be saved. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const requirement = finding.requirement;

  return (
    <Card className="border-white/10 bg-[#070e1b]/70 backdrop-blur-xl">
      <CardBody className="space-y-4 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <Code>{finding.requirement_code ?? "—"}</Code>
          <SeverityBadge severity={finding.severity} />
          {finding.ambiguous_terms.map((term) => (
            <Badge key={term} tone="high">
              “{term}”
            </Badge>
          ))}
          <div className="ml-auto flex items-center gap-3">
            <Confidence value={finding.confidence} />
            {finding.refinement_status && finding.refinement_status !== "pending" ? (
              <Badge tone={finding.refinement_status === "rejected" ? "neutral" : "ok"}>
                {finding.refinement_status}
              </Badge>
            ) : null}
          </div>
        </div>

        <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3.5">
          <p className="font-mono text-[10px] uppercase tracking-wider text-slate-500">Original Formulation</p>
          <p className="mt-1 text-xs leading-relaxed text-slate-200">
            {requirement?.original_text ?? "—"}
          </p>
          {requirement ? (
            <p className="mt-1.5 font-mono text-[10px] text-slate-500">
              Source Section: {requirement.section ?? "General"}
              {requirement.page_number ? ` · page ${requirement.page_number}` : ""}
            </p>
          ) : null}
        </div>

        {finding.evidence ? (
          <div className="rounded-lg border-l-2 border-amber-400 bg-amber-500/10 px-3 py-2 border-r border-t border-b border-amber-500/15">
            <p className="font-mono text-[10px] uppercase tracking-wider text-amber-300">Quoted Offending Term</p>
            <p className="mt-0.5 font-mono text-xs text-amber-100">“{finding.evidence}”</p>
          </div>
        ) : null}

        {finding.explanation ? (
          <div>
            <p className="font-mono text-[10px] uppercase tracking-wider text-slate-400">Why It Fails Testability</p>
            <p className="mt-1 text-xs leading-relaxed text-slate-300">{finding.explanation}</p>
          </div>
        ) : null}

        {finding.suggested_refinement ? (
          <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3.5">
            <p className="font-mono text-[10px] uppercase tracking-wider text-emerald-400">Proposed Measurable Refinement</p>
            {editing ? (
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                rows={3}
                className="mt-2 w-full rounded-xl border border-emerald-500/40 bg-[#02060f] p-2.5 text-xs text-white focus:border-emerald-400 focus:outline-none"
              />
            ) : (
              <p className="mt-1 text-xs leading-relaxed text-emerald-100">
                {finding.suggested_refinement}
              </p>
            )}

            {finding.refinement_id ? (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                {editing ? (
                  <>
                    <Button size="sm" variant="success" onClick={() => act("edit")} disabled={busy}>
                      <Check className="size-3.5" aria-hidden /> Save edit
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setEditing(false)} disabled={busy}>
                      Cancel
                    </Button>
                  </>
                ) : (
                  <>
                    <Button size="sm" variant="success" onClick={() => act("accept")} disabled={busy}>
                      <Check className="size-3.5" aria-hidden /> Accept Proposal
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => setEditing(true)} disabled={busy}>
                      <Pencil className="size-3.5" aria-hidden /> Edit
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => act("reject")} disabled={busy}>
                      <X className="size-3.5" aria-hidden /> Reject
                    </Button>
                  </>
                )}
                {busy ? <Spinner /> : null}
              </div>
            ) : null}
            {actionError ? <p className="mt-2 text-xs text-red-300">{actionError}</p> : null}
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}
