import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, X } from "lucide-react";
import { Button } from "@/components/ui";

interface HowItWorksModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const STEPS = [
  {
    title: "Upload",
    body: "A PDF, DOCX or TXT specification, up to 15 MB.",
  },
  {
    title: "Extract",
    body: "Each requirement is copied exactly as written, with its section and page. The original wording is never changed.",
  },
  {
    title: "Compare by meaning",
    body: "BAAI/bge-small-en-v1.5 embeddings rank requirement pairs by similarity, so only plausible duplicates and conflicts go to the language model.",
  },
  {
    title: "Verify with evidence",
    body: "Separate checks for ambiguity, contradictions, duplicates, missing detail and dependencies. Every finding quotes the text it is based on.",
  },
  {
    title: "Refine and trace",
    body: "Accept, edit or reject each suggested rewrite, then export the clean set. Every finding links back to the requirement it came from.",
  },
];

export function HowItWorksModal({ isOpen, onClose }: HowItWorksModalProps) {
  const navigate = useNavigate();
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="fixed inset-0 bg-[#02060f]/80 backdrop-blur-md"
        onClick={onClose}
        aria-hidden="true"
      />

      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="how-it-works-title"
        className="relative max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-white/20 bg-[#070e1b]/90 p-7 shadow-[0_20px_60px_rgba(0,0,0,0.7)] backdrop-blur-2xl"
      >
        <div className="pointer-events-none absolute -top-24 left-1/2 h-48 w-80 -translate-x-1/2 rounded-full bg-gradient-to-r from-amber-500/20 via-sky-500/20 to-indigo-500/20 blur-3xl" />

        <button
          ref={closeRef}
          onClick={onClose}
          className="absolute right-5 top-5 rounded-full p-1.5 text-slate-400 transition-colors hover:bg-white/10 hover:text-white"
          aria-label="Close"
        >
          <X className="size-5" />
        </button>

        <h2 id="how-it-works-title" className="font-sans text-xl font-semibold text-white">
          How ReqGuard AI works
        </h2>
        <p className="mt-1 text-xs text-slate-400">
          A pipeline of separate stages, not one prompt. Each stage can be tested on its own.
        </p>

        <ol className="mt-6 space-y-4">
          {STEPS.map((step, index) => (
            <li key={step.title} className="flex gap-3">
              <span className="flex size-6 flex-none items-center justify-center rounded-full border border-sky-400/40 bg-sky-500/10 font-mono text-[11px] text-sky-300">
                {index + 1}
              </span>
              <div>
                <p className="text-sm font-semibold text-white">{step.title}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-slate-400">{step.body}</p>
              </div>
            </li>
          ))}
        </ol>

        <p className="mt-6 rounded-xl border border-white/10 bg-white/[0.03] px-3.5 py-2.5 text-[11px] leading-relaxed text-slate-400">
          On a free Groq key, the 48-requirement sample takes about 13 minutes to analyse, because
          the provider allows 8,000 tokens per minute.
        </p>

        <Button
          className="mt-5 w-full justify-center text-sm font-semibold"
          onClick={() => {
            onClose();
            navigate("/upload");
          }}
        >
          Analyze a document
          <ArrowRight className="size-4" />
        </Button>
      </div>
    </div>
  );
}
