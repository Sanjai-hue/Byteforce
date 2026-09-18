/** Shared UI primitives, styled with the dark glassmorphic NEURAL design system. */

import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { Severity } from "@/types/api";

/* ------------------------------------------------------------------ Button */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-all duration-200 disabled:pointer-events-none disabled:opacity-50 cursor-pointer",
  {
    variants: {
      variant: {
        primary:
          "cta-glass text-white font-medium border border-white/30 shadow-[0_0_20px_rgba(56,189,248,0.2)] hover:shadow-[0_0_30px_rgba(56,189,248,0.4)] active:scale-[0.98]",
        secondary:
          "bg-white/[0.05] text-white border border-white/15 backdrop-blur-md hover:bg-white/[0.1] hover:border-white/30 active:scale-[0.98]",
        ghost:
          "text-ink-soft hover:text-white hover:bg-white/[0.07] active:scale-[0.98]",
        danger:
          "bg-red-500/20 text-red-200 border border-red-500/40 hover:bg-red-500/30 hover:shadow-[0_0_20px_rgba(239,68,68,0.3)] active:scale-[0.98]",
        success:
          "bg-emerald-500/20 text-emerald-200 border border-emerald-500/40 hover:bg-emerald-500/30 hover:shadow-[0_0_20px_rgba(16,185,129,0.3)] active:scale-[0.98]",
      },
      size: {
        sm: "h-8 px-3 text-xs rounded-md",
        md: "h-10 px-4",
        lg: "h-12 px-6 text-base rounded-xl",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

/* -------------------------------------------------------------------- Card */
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("glass-card rounded-xl border border-line text-white", className)}
      {...props}
    />
  );
}

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("border-b border-line/60 px-5 py-4", className)} {...props} />;
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-sm font-semibold tracking-tight text-white", className)} {...props} />;
}

export function CardBody({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-5 py-4", className)} {...props} />;
}

/* ------------------------------------------------------------------- Badge */
const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium whitespace-nowrap backdrop-blur-sm",
  {
    variants: {
      tone: {
        neutral: "bg-white/[0.06] text-ink-soft border border-white/10",
        brand: "bg-sky-500/15 text-sky-300 border border-sky-500/30 shadow-[0_0_12px_rgba(56,189,248,0.15)]",
        critical: "bg-red-500/15 text-red-300 border border-red-500/30 shadow-[0_0_12px_rgba(239,68,68,0.15)]",
        high: "bg-amber-500/15 text-amber-300 border border-amber-500/30 shadow-[0_0_12px_rgba(245,158,11,0.15)]",
        medium: "bg-yellow-500/15 text-yellow-300 border border-yellow-500/30",
        low: "bg-blue-500/15 text-blue-300 border border-blue-500/30",
        ok: "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 shadow-[0_0_12px_rgba(16,185,129,0.15)]",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function Badge({
  className,
  tone,
  ...props
}: HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <Badge tone={severity}>{severity}</Badge>;
}

/* -------------------------------------------------------- Requirement code */
export function Code({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "rounded bg-white/[0.08] px-2 py-0.5 font-mono text-xs font-semibold text-sky-300 border border-white/10",
        className,
      )}
    >
      {children}
    </span>
  );
}

/* ------------------------------------------------------------ Empty states */
export function EmptyState({
  icon,
  title,
  description,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-white/15 bg-white/[0.02] backdrop-blur-md px-6 py-14 text-center">
      {icon ? <div className="mb-3 text-sky-400">{icon}</div> : null}
      <p className="text-sm font-medium text-white">{title}</p>
      {description ? <p className="mt-1 max-w-md text-sm text-ink-soft">{description}</p> : null}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cn(
        "inline-block size-4 animate-spin rounded-full border-2 border-white/20 border-t-sky-400",
        className,
      )}
    />
  );
}

export function ErrorNotice({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-5 py-4 backdrop-blur-md">
      <p className="text-sm font-medium text-red-200">{message}</p>
      {onRetry ? (
        <Button variant="secondary" size="sm" className="mt-3" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------- Progress bar */
export function ProgressBar({ value }: { value: number }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div
      className="h-2 w-full overflow-hidden rounded-full bg-white/10"
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="h-full rounded-full bg-gradient-to-r from-amber-400 via-sky-400 to-indigo-500 transition-[width] duration-500 ease-out shadow-[0_0_12px_rgba(56,189,248,0.5)]"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

/* --------------------------------------------------------------- Confidence */
export function Confidence({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className="text-xs text-ink-muted">—</span>;
  const pct = Math.round(value * 100);
  return (
    <span className="inline-flex items-center gap-1.5" title={`AI confidence ${pct}%`}>
      <span className="h-1.5 w-12 overflow-hidden rounded-full bg-white/10">
        <span className="block h-full rounded-full bg-gradient-to-r from-sky-400 to-indigo-400 shadow-[0_0_8px_rgba(56,189,248,0.4)]" style={{ width: `${pct}%` }} />
      </span>
      <span className="font-mono text-xs text-sky-200">{pct}%</span>
    </span>
  );
}
