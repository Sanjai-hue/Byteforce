import { ArrowLeft, FileText, UploadCloud, X, Sparkles, CheckCircle2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button, Card, CardBody, ErrorNotice, ProgressBar, Spinner } from "@/components/ui";
import { rememberLastDocument } from "@/lib/lastDocument";
import { formatBytes } from "@/lib/utils";
import { ApiError, api } from "@/services/api";
import type { AnalysisStatus } from "@/types/api";

const ACCEPTED = ".pdf,.docx,.txt";
const POLL_MS = 2500;
const SAMPLE_NAME = "ECommerce_SRS_Hackathon_Sample.docx";
const SAMPLE_URL = `/samples/${SAMPLE_NAME}`;
const DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export function Upload() {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<"idle" | "uploading" | "analyzing">("idle");
  const [status, setStatus] = useState<AnalysisStatus | null>(null);
  const documentIdRef = useRef<string | null>(null);

  const choose = useCallback((candidate: File | undefined | null) => {
    if (!candidate) return;
    const extension = candidate.name.split(".").pop()?.toLowerCase() ?? "";
    if (!["pdf", "docx", "txt"].includes(extension)) {
      setError("That file type is not supported. Upload a PDF, DOCX or TXT specification.");
      return;
    }
    setError(null);
    setFile(candidate);
  }, []);

  // Poll analysis progress until it finishes, then move to the dashboard.
  useEffect(() => {
    if (phase !== "analyzing" || !documentIdRef.current) return;
    const documentId = documentIdRef.current;
    let cancelled = false;

    const tick = async () => {
      try {
        const next = await api.getStatus(documentId);
        if (cancelled) return;
        setStatus(next);
        if (next.status === "completed") {
          rememberLastDocument(documentId);
          navigate(`/dashboard/${documentId}`);
          return;
        }
        if (next.status === "failed") {
          setPhase("idle");
          setError(next.error_message ?? "The analysis failed. Check the document and try again.");
          return;
        }
        window.setTimeout(tick, POLL_MS);
      } catch (caught) {
        if (cancelled) return;
        setPhase("idle");
        setError(
          caught instanceof ApiError ? caught.message : "Lost contact with the analysis service.",
        );
      }
    };

    void tick();
    return () => {
      cancelled = true;
    };
  }, [phase, navigate]);

  const start = async () => {
    if (!file) return;
    setError(null);
    setPhase("uploading");
    try {
      const uploaded = await api.uploadDocument(file);
      documentIdRef.current = uploaded.document_id;
      await api.startAnalysis(uploaded.document_id);
      setPhase("analyzing");
    } catch (caught) {
      setPhase("idle");
      setError(caught instanceof ApiError ? caught.message : "The upload failed. Try again.");
    }
  };

  // The real 48-requirement sample the evaluation labels were written for,
  // served from /public so it is the same file a judge can download.
  const [loadingSample, setLoadingSample] = useState(false);
  const loadSampleDoc = async () => {
    setLoadingSample(true);
    setError(null);
    try {
      const response = await fetch(SAMPLE_URL);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const blob = await response.blob();
      choose(new File([blob], SAMPLE_NAME, { type: DOCX_TYPE }));
    } catch {
      setError("The sample document could not be loaded. Use Browse Files instead.");
    } finally {
      setLoadingSample(false);
    }
  };

  const busy = phase !== "idle";

  return (
    <div className="min-h-screen bg-[#02060f] text-white">
      {/* Background Ambient Glow */}
      <div className="pointer-events-none fixed inset-0 z-0">
        <div className="absolute top-10 left-1/2 h-[450px] w-[800px] -translate-x-1/2 rounded-full bg-gradient-to-b from-sky-500/10 via-indigo-500/5 to-transparent blur-[140px]" />
      </div>

      {/* Header */}
      <header className="relative z-10 border-b border-white/10 bg-[#070e1b]/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-4xl items-center justify-between px-6">
          <Link
            to="/"
            className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3.5 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:border-white/25 hover:bg-white/[0.08] hover:text-white"
          >
            <ArrowLeft className="size-3.5" aria-hidden />
            Back to home
          </Link>
          <Link to="/" className="flex items-center gap-2">
            <svg className="h-4 w-5.5 fill-white" viewBox="0 0 23 17" aria-hidden="true">
              <path d="M8.15 0.9 L4.55 0.9 L0.5 9.3 L4.1 9.3 Z" />
              <path d="M17.0 0 L13.4 0 L6.15 16.4 L9.75 16.4 Z" />
              <path d="M22.9 0 L19.3 0 L15.0 7.6 L18.6 7.6 Z" />
              <path d="M22.6 6.9 L19.0 6.9 L14.05 16.4 L17.65 16.4 Z" />
            </svg>
            <span className="font-sans text-xs font-bold tracking-[0.12em] text-white">
              ReqGuard <span className="text-sky-400">AI</span>
            </span>
          </Link>
        </div>
      </header>

      {/* Main Container */}
      <main className="relative z-10 mx-auto max-w-3xl px-6 py-14">
        {/* Title */}
        <div className="text-center sm:text-left">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-400/30 bg-sky-500/10 px-3 py-1 text-xs font-medium text-sky-300 shadow-[0_0_12px_rgba(56,189,248,0.2)]">
            <Sparkles className="size-3" />
            AI Specification Ingestion
          </span>
          <h1 className="mt-4 font-sans text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            Upload Software Requirements Specification
          </h1>
          <p className="mt-2.5 text-sm text-slate-400">
            ReqGuard scans for ambiguities, contradictions, duplicates, and topological dependencies
            with cited textual evidence.
          </p>
        </div>

        {error ? (
          <div className="mt-6">
            <ErrorNotice message={error} />
          </div>
        ) : null}

        {phase === "analyzing" && status ? (
          <Card className="mt-8 border-sky-400/30 bg-[#070e1b]/80 shadow-[0_0_40px_rgba(56,189,248,0.15)]">
            <CardBody className="p-8">
              <div className="flex items-center gap-4">
                <Spinner className="size-6 border-sky-500/30 border-t-sky-400" />
                <div className="min-w-0 flex-1">
                  <p className="font-sans text-base font-semibold text-white">{status.stage_label}</p>
                  <p className="mt-0.5 text-xs text-slate-400">
                    Analysing {file?.name}. Keep this page open: the report opens when it finishes.
                    The 48-requirement sample takes about 13 minutes on a free Groq key.
                  </p>
                </div>
                <span className="font-mono text-base font-bold text-sky-400">{status.progress}%</span>
              </div>

              <div className="mt-6">
                <ProgressBar value={status.progress} />
              </div>

              {status.stats?.requirements ? (
                <div className="mt-4 flex items-center gap-2 text-xs text-slate-400">
                  <CheckCircle2 className="size-3.5 text-emerald-400" />
                  <span>{status.stats.requirements} requirements extracted & vectorized so far.</span>
                </div>
              ) : null}
            </CardBody>
          </Card>
        ) : (
          <>
            {/* Upload Drag & Drop Area */}
            <div
              onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragging(false);
                choose(event.dataTransfer.files?.[0]);
              }}
              className={`mt-8 rounded-2xl border-2 border-dashed p-12 text-center transition-all ${
                dragging
                  ? "border-sky-400 bg-sky-500/10 shadow-[0_0_30px_rgba(56,189,248,0.25)]"
                  : "border-white/15 bg-white/[0.02] hover:border-white/30 hover:bg-white/[0.04]"
              }`}
            >
              <div className="mx-auto flex size-14 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.05] shadow-inner">
                <UploadCloud className="size-7 text-sky-400" aria-hidden />
              </div>
              <p className="mt-4 font-sans text-base font-medium text-white">
                Drag your specification document here, or
              </p>
              <Button
                variant="secondary"
                size="md"
                className="mt-4 text-xs font-semibold uppercase tracking-wider"
                onClick={() => inputRef.current?.click()}
                disabled={busy}
              >
                Browse Files
              </Button>
              <input
                ref={inputRef}
                type="file"
                accept={ACCEPTED}
                className="sr-only"
                onChange={(event) => choose(event.target.files?.[0])}
              />
              <p className="mt-3 text-xs text-slate-500">PDF, DOCX or TXT files up to 15 MB</p>

              {/* Fast track sample load button */}
              <div className="mt-6 border-t border-white/10 pt-5">
                <button
                  type="button"
                  onClick={loadSampleDoc}
                  disabled={busy || loadingSample}
                  className="inline-flex items-center gap-2 rounded-full border border-sky-400/25 bg-sky-500/10 px-4 py-1.5 text-xs font-medium text-sky-200 transition-colors hover:border-sky-400/50 hover:bg-sky-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {loadingSample ? (
                    <Spinner className="size-3.5" />
                  ) : (
                    <Sparkles className="size-3.5 text-amber-400" />
                  )}
                  <span>Use the sample E-Commerce SRS (48 requirements, DOCX)</span>
                </button>
              </div>
            </div>

            {/* Selected File Card */}
            {file ? (
              <div className="mt-5 overflow-hidden rounded-xl border border-sky-400/30 bg-[#070e1b]/80 p-4 shadow-lg backdrop-blur-md">
                <div className="flex items-center gap-3">
                  <div className="flex size-10 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-400/20">
                    <FileText className="size-5 text-sky-400" aria-hidden />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-sans text-sm font-semibold text-white">{file.name}</p>
                    <p className="text-xs text-slate-400">
                      {formatBytes(file.size)} · {file.name.split(".").pop()?.toUpperCase()} Document
                    </p>
                  </div>
                  <button
                    onClick={() => setFile(null)}
                    aria-label="Remove file"
                    className="rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-white/10 hover:text-white"
                    disabled={busy}
                  >
                    <X className="size-4" aria-hidden />
                  </button>
                </div>
              </div>
            ) : null}

            {/* Action Bar */}
            <div className="mt-8 flex items-center justify-between border-t border-white/10 pt-6">
              <span className="max-w-xs text-xs text-slate-500">
                Requirement text is sent to the configured AI provider for analysis.
              </span>
              <Button
                size="lg"
                onClick={start}
                disabled={!file || busy}
                className="px-8 font-semibold tracking-wide"
              >
                {phase === "uploading" ? (
                  <Spinner className="mr-2 border-white/30 border-t-white" />
                ) : (
                  <Sparkles className="mr-2 size-4 text-amber-300" />
                )}
                Analyze Requirements
              </Button>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
