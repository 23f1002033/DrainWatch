"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { userMessage } from "@/lib/errors";
import { STATUS_LABEL, type Severity, type Status } from "@/lib/types";

const SEVERITY_CLASS: Record<Severity, string> = {
  S1: "bg-red-100 text-red-800 ring-red-200",
  S2: "bg-amber-100 text-amber-900 ring-amber-200",
  S3: "bg-slate-100 text-slate-700 ring-slate-200",
};

export function SeverityBadge({ severity }: { severity: Severity | null }) {
  if (!severity) return <span className="text-xs text-slate-400">Untriaged</span>;
  return (
    <span className={`inline-flex rounded px-1.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${SEVERITY_CLASS[severity]}`}>
      {severity}
    </span>
  );
}

const STATUS_CLASS: Record<Status, string> = {
  reported: "border-slate-300 text-slate-700",
  triaged: "border-slate-400 text-slate-800",
  assigned: "border-blue-300 text-blue-800",
  in_progress: "border-blue-500 text-blue-900 bg-blue-50",
  resolved: "border-emerald-400 text-emerald-800",
  closed: "border-slate-300 text-slate-500 bg-slate-100",
};

export function StatusChip({ status }: { status: Status }) {
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${STATUS_CLASS[status]}`}>
      {STATUS_LABEL[status]}
    </span>
  );
}

type Variant = "primary" | "secondary" | "danger";
const VARIANT: Record<Variant, string> = {
  primary: "bg-accent text-white hover:bg-accent-hover disabled:bg-slate-300 disabled:text-slate-600",
  secondary: "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50 disabled:text-slate-400",
  danger: "border border-red-300 bg-white text-red-700 hover:bg-red-50 disabled:text-slate-400",
};

export function Button({
  variant = "secondary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      {...props}
      className={`inline-flex min-h-10 items-center justify-center rounded-md px-3 text-sm font-medium disabled:cursor-not-allowed ${VARIANT[variant]} ${className}`}
    />
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 py-6 text-sm text-slate-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600" aria-hidden />
      {label}
    </div>
  );
}

export function ErrorBox({
  error,
  message,
  onRetry,
  children,
}: {
  error?: unknown;
  message?: string;
  onRetry?: () => void;
  children?: ReactNode;
}) {
  return (
    <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
      <p>{message ?? userMessage(error)}</p>
      {children}
      {onRetry && (
        <Button className="mt-2" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-md border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">{children}</div>;
}

export function Field({
  label,
  htmlFor,
  error,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  error?: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="block text-sm font-medium text-slate-800">
        {label}
      </label>
      {children}
      {hint && !error && <p className="text-xs text-slate-500">{hint}</p>}
      {error && (
        <p id={`${htmlFor}-error`} className="text-xs text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}

export const inputClass =
  "block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 placeholder:text-slate-400 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent aria-[invalid=true]:border-red-500";
