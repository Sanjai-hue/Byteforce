/** Contradiction and duplicate reports — both show a requirement pair side by side in NEURAL dark glass. */

import { Copy, ShieldAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Badge,
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
import type { PairFinding, Requirement } from "@/types/api";

function RequirementPanel({
  code,
  requirement,
  evidence,
  accent,
}: {
  code: string | null;
  requirement: Requirement | null;
  evidence: string | null;
  accent: string;
}) {
  return (
    <div className={`flex-1 rounded-xl border border-white/10 bg-[#02060f]/60 p-4 transition-all hover:border-white/20`}>
      <div className="flex items-center gap-2">
        <Code>{code ?? "—"}</Code>
        {requirement?.requirement_type ? (
          <Badge tone="neutral">{requirement.requirement_type.replace("_", " ")}</Badge>
        ) : null}
      </div>
      <p className="mt-2.5 text-xs leading-relaxed text-slate-200">
        {requirement?.original_text ?? "Requirement text unavailable"}
      </p>
      {requirement ? (
        <p className="mt-2 font-mono text-[10px] text-slate-500">
          {requirement.section ?? "General Specification"}
          {requirement.page_number ? ` · page ${requirement.page_number}` : ""}
        </p>
      ) : null}
      {evidence ? (
        <div className={`mt-3 rounded-lg border-l-2 ${accent} bg-white/[0.03] px-3 py-2 border-r border-t border-b border-white/5`}>
          <p className="font-mono text-[10px] uppercase tracking-wider text-slate-400">Cited Clause Evidence</p>
          <p className="mt-0.5 font-mono text-xs text-sky-200">“{evidence}”</p>
        </div>
      ) : null}
    </div>
  );
}

function PairCard({ finding, kind }: { finding: PairFinding; kind: "contradiction" | "duplicate" }) {
  const accent = kind === "contradiction" ? "border-red-400" : "border-amber-400";
  return (
    <Card className="border-white/10 bg-[#070e1b]/70 backdrop-blur-xl">
      <CardBody className="space-y-4 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge severity={finding.severity} />
          {finding.classification ? (
            <Badge tone={kind === "contradiction" ? "critical" : "medium"}>
              {finding.classification.replace(/_/g, " ")}
            </Badge>
          ) : null}
          {finding.conflict_type ? <Badge tone="neutral">{finding.conflict_type}</Badge> : null}
          {finding.similarity_score != null ? (
            <Badge tone="neutral">cos-sim {finding.similarity_score.toFixed(2)}</Badge>
          ) : null}
          <div className="ml-auto">
            <Confidence value={finding.confidence} />
          </div>
        </div>

        <div className="flex flex-col gap-3 lg:flex-row lg:items-stretch">
          <RequirementPanel
            code={finding.code_a}
            requirement={finding.requirement_a}
            evidence={finding.evidence_a}
            accent={accent}
          />
          <div className="flex items-center justify-center lg:w-12">
            <span className="flex size-8 items-center justify-center rounded-full border border-white/20 bg-white/[0.06] font-mono text-xs font-bold text-sky-300 shadow-[0_0_10px_rgba(56,189,248,0.2)]">
              {kind === "contradiction" ? "VS" : "≈"}
            </span>
          </div>
          <RequirementPanel
            code={finding.code_b}
            requirement={finding.requirement_b}
            evidence={finding.evidence_b}
            accent={accent}
          />
        </div>

        {finding.description || finding.reason ? (
          <div className="rounded-xl border border-white/5 bg-white/[0.02] p-3.5">
            <p className="font-mono text-[10px] uppercase tracking-wider text-slate-400">
              {kind === "contradiction" ? "Why They Contradict" : "Why They Duplicate"}
            </p>
            <p className="mt-1 text-xs leading-relaxed text-slate-300">
              {finding.description || finding.reason}
            </p>
          </div>
        ) : null}

        {finding.recommendation ? (
          <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3.5">
            <p className="font-mono text-[10px] uppercase tracking-wider text-emerald-400">
              {kind === "contradiction" ? "Suggested Resolution" : "Recommendation"}
            </p>
            <p className="mt-1 text-xs leading-relaxed text-emerald-100">{finding.recommendation}</p>
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

export function Contradictions() {
  const { documentId = "" } = useParams();
  const { data, loading, error, refresh } = useAsync(
    () => api.getContradictions(documentId),
    [documentId],
  );
  const [onlyStrict, setOnlyStrict] = useState(false);

  const rows = useMemo(() => {
    const all = data?.contradictions ?? [];
    const filtered = onlyStrict ? all.filter((row) => row.classification === "contradiction") : all;
    return [...filtered].sort((a, b) => b.confidence - a.confidence);
  }, [data, onlyStrict]);

  if (loading)
    return (
      <div className="flex items-center gap-3 py-20 text-sm text-slate-400">
        <Spinner /> Loading contradiction intelligence…
      </div>
    );
  if (error) return <ErrorNotice message={error} onRetry={refresh} />;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-sans text-2xl font-bold tracking-tight text-white">Contradiction Report</h1>
          <p className="mt-1 text-xs text-slate-400">
            Requirement pairs that cannot both be satisfied by one software implementation.
          </p>
        </div>
        <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer">
          <input
            type="checkbox"
            checked={onlyStrict}
            onChange={(event) => setOnlyStrict(event.target.checked)}
            className="size-4 rounded border-white/20 bg-[#070e1b] accent-sky-500"
          />
          <span>Direct contradictions only</span>
        </label>
      </div>

      {rows.length === 0 ? (
        <EmptyState
          icon={<ShieldAlert className="size-6 text-emerald-400" />}
          title="No contradictions reported"
          description="All requirement statements can coexist logically without conflict."
        />
      ) : (
        <div className="space-y-4">
          {rows.map((finding) => (
            <PairCard key={finding.issue_id} finding={finding} kind="contradiction" />
          ))}
        </div>
      )}
    </div>
  );
}

export function Duplicates() {
  const { documentId = "" } = useParams();
  const { data, loading, error, refresh } = useAsync(
    () => api.getDuplicates(documentId),
    [documentId],
  );

  if (loading)
    return (
      <div className="flex items-center gap-3 py-20 text-sm text-slate-400">
        <Spinner /> Loading duplicate intelligence…
      </div>
    );
  if (error) return <ErrorNotice message={error} onRetry={refresh} />;

  const rows = [...(data?.duplicates ?? [])].sort((a, b) => b.confidence - a.confidence);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-sans text-2xl font-bold tracking-tight text-white">Duplicate Report</h1>
        <p className="mt-1 text-xs text-slate-400">
          Pairs selected by 384-dim embedding similarity, then verified by the LLM reasoning core.
        </p>
      </div>

      {rows.length === 0 ? (
        <EmptyState
          icon={<Copy className="size-6 text-emerald-400" />}
          title="No duplicates reported"
          description="All requirements describe unique, distinct capabilities."
        />
      ) : (
        <div className="space-y-4">
          {rows.map((finding) => (
            <PairCard key={finding.issue_id} finding={finding} kind="duplicate" />
          ))}
        </div>
      )}
    </div>
  );
}
