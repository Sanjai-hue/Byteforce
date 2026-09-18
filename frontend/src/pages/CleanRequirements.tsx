import { Check, Download, HelpCircle, ListChecks, Pencil, X } from "lucide-react";
import { useState } from "react";
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
import { ApiError, api } from "@/services/api";
import { useAsync } from "@/hooks/useApi";
import type { CleanRequirement, MissingInfoFinding } from "@/types/api";

const STATUS_TONE: Record<string, "ok" | "critical" | "medium" | "neutral"> = {
  refined: "ok",
  unchanged: "neutral",
  needs_review: "medium",
  merged_duplicate: "neutral",
  contradiction_unresolved: "critical",
};

export function CleanRequirements() {
  const { documentId = "" } = useParams();
  const { data, loading, error, refresh } = useAsync(
    () => api.getCleanRequirements(documentId),
    [documentId],
  );

  if (loading)
    return (
      <div className="flex items-center gap-3 py-20 text-sm text-slate-400">
        <Spinner /> Loading clean requirement set…
      </div>
    );
  if (error) return <ErrorNotice message={error} onRetry={refresh} />;
  if (!data) return null;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-sans text-2xl font-bold tracking-tight text-white">Clean Requirement Set</h1>
          <p className="mt-1 text-xs text-slate-400">
            {data.included} of {data.total} requirements included · {data.merged_duplicates} merged
            as duplicates · {data.unresolved_contradictions} unresolved contradictions
          </p>
        </div>
        <a href={api.exportMarkdownUrl(documentId)} target="_blank" rel="noreferrer">
          <Button size="md" className="shadow-[0_0_20px_rgba(56,189,248,0.2)]">
            <Download className="size-4" aria-hidden />
            Export Clean SRS (Markdown)
          </Button>
        </a>
      </div>

      <p className="rounded-xl border border-white/10 bg-[#070e1b]/50 px-4 py-3 text-xs text-slate-400 backdrop-blur-md">
        The original author wording is strictly immutable. A refinement proposal only replaces the active export text once accepted.
      </p>

      {data.requirements.length === 0 ? (
        <EmptyState icon={<ListChecks className="size-6" />} title="No requirements extracted" />
      ) : (
        <div className="space-y-3">
          {data.requirements.map((item) => (
            <CleanRow key={item.original_requirement_id} item={item} onChanged={refresh} />
          ))}
        </div>
      )}
    </div>
  );
}

function CleanRow({ item, onChanged }: { item: CleanRequirement; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const refinementState = item.refinement_status;
  const applied = refinementState === "accepted" || refinementState === "edited";
  const panel = rightPanel(item);

  const startEditing = () => {
    setDraft(item.proposed_text ?? item.refined_text);
    setEditing(true);
  };

  const act = async (action: "accept" | "reject" | "edit") => {
    if (!item.refinement_id) return;
    if (action === "edit" && !draft.trim()) {
      setActionError("The edited requirement cannot be empty.");
      return;
    }
    setBusy(true);
    setActionError(null);
    try {
      if (action === "accept") await api.acceptRefinement(item.refinement_id);
      if (action === "reject") await api.rejectRefinement(item.refinement_id);
      if (action === "edit") await api.editRefinement(item.refinement_id, draft.trim());
      setEditing(false);
      onChanged();
    } catch (caught) {
      setActionError(
        caught instanceof ApiError ? caught.message : "That change could not be saved. Try again.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className={`border-white/10 bg-[#070e1b]/70 backdrop-blur-xl ${item.included ? "" : "opacity-60"}`}>
      <CardBody className="space-y-3 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <Code>{item.requirement_code}</Code>
          <Badge tone="neutral">{item.requirement_type.replace("_", " ")}</Badge>
          <Badge tone={STATUS_TONE[item.status] ?? "neutral"}>
            {item.status.replace(/_/g, " ")}
          </Badge>
          {!item.included ? <Badge tone="neutral">excluded from export</Badge> : null}
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-white/5 bg-white/[0.02] p-3">
            <p className="font-mono text-[10px] uppercase tracking-wider text-slate-500">Original Formulation</p>
            <p className="mt-1 text-xs leading-relaxed text-slate-300">{item.original_text}</p>
          </div>
          <div className={`rounded-lg border p-3 ${panel.frame}`}>
            <p className={`font-mono text-[10px] uppercase tracking-wider ${panel.labelTone}`}>
              {editing ? "Editing proposed rewrite" : panel.label}
            </p>
            {editing ? (
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                rows={3}
                aria-label={`Edit the rewrite for ${item.requirement_code}`}
                className="mt-1.5 w-full rounded-lg border border-sky-400/40 bg-[#02060f] p-2.5 text-xs text-white focus:border-sky-400 focus:outline-none"
              />
            ) : (
              <p className={`mt-1 text-xs leading-relaxed ${panel.textTone}`}>{panel.text}</p>
            )}
          </div>
        </div>

        {item.reason ? (
          <p className="text-xs text-slate-400">
            <span className="font-mono text-[10px] uppercase tracking-wider text-slate-500">Reason: </span>
            {item.reason}
          </p>
        ) : null}

        {actionError ? (
          <p role="alert" className="text-xs text-red-300">
            {actionError}
          </p>
        ) : null}

        {item.refinement_id ? (
          <div className="flex flex-wrap items-center gap-2 border-t border-white/10 pt-3">
            {editing ? (
              <>
                <Button size="sm" variant="success" onClick={() => act("edit")} disabled={busy}>
                  <Check className="size-3.5" aria-hidden /> Save and apply
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setEditing(false)} disabled={busy}>
                  Cancel
                </Button>
              </>
            ) : (
              <>
                {!applied ? (
                  <Button size="sm" variant="success" onClick={() => act("accept")} disabled={busy}>
                    <Check className="size-3.5" aria-hidden />
                    {refinementState === "rejected" ? "Accept proposal after all" : "Accept proposal"}
                  </Button>
                ) : null}
                <Button size="sm" variant="secondary" onClick={startEditing} disabled={busy}>
                  <Pencil className="size-3.5" aria-hidden /> Edit
                </Button>
                {refinementState !== "rejected" ? (
                  <Button size="sm" variant="ghost" onClick={() => act("reject")} disabled={busy}>
                    <X className="size-3.5" aria-hidden />
                    {applied ? "Revert to original" : "Reject"}
                  </Button>
                ) : null}
              </>
            )}
            {busy ? <Spinner /> : null}
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

/** What the right-hand panel shows for each refinement state. */
function rightPanel(item: CleanRequirement) {
  switch (item.refinement_status) {
    case "pending":
      return {
        label: "Proposed rewrite · not applied yet",
        text: item.proposed_text ?? "",
        frame: "border-amber-400/25 bg-amber-500/[0.04]",
        labelTone: "text-amber-300",
        textTone: "text-white",
      };
    case "accepted":
    case "edited":
      return {
        label: item.refinement_status === "edited" ? "In force · your edit" : "In force · accepted rewrite",
        text: item.refined_text,
        frame: "border-emerald-400/25 bg-emerald-500/[0.04]",
        labelTone: "text-emerald-300",
        textTone: "text-white font-medium",
      };
    case "rejected":
      return {
        label: "Proposal rejected · original kept",
        text: item.proposed_text ?? "",
        frame: "border-white/10 bg-white/[0.02]",
        labelTone: "text-slate-500",
        textTone: "text-slate-500 line-through decoration-slate-600",
      };
    default:
      return {
        label: "No rewrite proposed",
        text: item.refined_text,
        frame: "border-white/5 bg-white/[0.02]",
        labelTone: "text-slate-500",
        textTone: "text-slate-400",
      };
  }
}

export function MissingInformation() {
  const { documentId = "" } = useParams();
  const { data, loading, error, refresh } = useAsync(
    () => api.getMissingInformation(documentId),
    [documentId],
  );

  if (loading)
    return (
      <div className="flex items-center gap-3 py-20 text-sm text-slate-400">
        <Spinner /> Loading missing information…
      </div>
    );
  if (error) return <ErrorNotice message={error} onRetry={refresh} />;

  const rows = data?.missing_information ?? [];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-sans text-2xl font-bold tracking-tight text-white">Missing Information</h1>
        <p className="mt-1 text-xs text-slate-400">
          Omitted details, boundary cases, and unstated parameters engineers would have to guess.
        </p>
      </div>

      {rows.length === 0 ? (
        <EmptyState
          icon={<HelpCircle className="size-6" />}
          title="No missing information detected"
          description="All extracted requirements contain adequate operational parameters."
        />
      ) : (
        <div className="space-y-4">
          {rows.map((finding) => (
            <MissingInfoCard key={finding.issue_id} finding={finding} />
          ))}
        </div>
      )}
    </div>
  );
}

function MissingInfoCard({ finding }: { finding: MissingInfoFinding }) {
  return (
    <Card className="border-white/10 bg-[#070e1b]/70 backdrop-blur-xl">
      <CardBody className="space-y-3.5 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <Code>{finding.requirement?.requirement_code ?? "—"}</Code>
          <SeverityBadge severity={finding.severity} />
          <div className="ml-auto">
            <Confidence value={finding.confidence} />
          </div>
        </div>

        <p className="text-xs leading-relaxed text-slate-200">
          {finding.requirement?.original_text ?? "—"}
        </p>

        <div>
          <p className="font-mono text-[10px] uppercase tracking-wider text-slate-500">Missing Specifications</p>
          <ul className="mt-1.5 flex flex-wrap gap-1.5">
            {finding.missing_information.map((item) => (
              <li key={item}>
                <Badge tone="medium">{item}</Badge>
              </li>
            ))}
          </ul>
        </div>

        {finding.suggested_questions.length > 0 ? (
          <div>
            <p className="font-mono text-[10px] uppercase tracking-wider text-slate-500">Follow-up Clarifications</p>
            <ul className="mt-1.5 list-disc space-y-1 pl-5 text-xs text-slate-400">
              {finding.suggested_questions.map((question) => (
                <li key={question}>{question}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {finding.suggested_refinement ? (
          <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 p-3.5">
            <p className="font-mono text-[10px] uppercase tracking-wider text-emerald-400">Proposed Complete Requirement</p>
            <p className="mt-1 text-xs leading-relaxed text-emerald-100">{finding.suggested_refinement}</p>
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}
