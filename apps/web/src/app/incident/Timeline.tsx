import { formatTime } from "@/lib/format";
import { STATUS_LABEL, type IncidentEvent, type Status } from "@/lib/types";

const ACTION_LABEL: Record<string, string> = {
  report: "Reported",
  triage: "Triaged",
  assign: "Assigned",
  start: "Started work",
  resolve: "Resolved",
  close: "Verified and closed",
  verification_failed: "Verification failed",
  reopen: "Reopened",
  add_evidence: "Added photo",
};

const ROLE_LABEL: Record<string, string> = { operator: "Operator", field_worker: "Field worker", public: "Public" };

const FIELDS = ["status", "severity", "assigned_to", "resolution_summary"] as const;
const FIELD_LABEL: Record<(typeof FIELDS)[number], string> = {
  status: "Status",
  severity: "Severity",
  assigned_to: "Assignee",
  resolution_summary: "Summary",
};

export function Timeline({
  events,
  nameOf,
  knownName,
}: {
  events: IncidentEvent[];
  nameOf: (sub: string | null) => string;
  knownName: (sub: string) => string | null;
}) {
  if (events.length === 0) return <p className="mt-3 text-sm text-slate-500">No events recorded.</p>;

  function show(field: (typeof FIELDS)[number], value: unknown): string {
    if (value === null || value === undefined || value === "") return "none";
    if (field === "status") return STATUS_LABEL[value as Status] ?? String(value);
    if (field === "assigned_to") return nameOf(String(value));
    return String(value);
  }

  return (
    <ol className="mt-3 space-y-3 border-l border-slate-200 pl-4">
      {[...events].reverse().map((e) => {
        const changes = FIELDS.filter(
          (f) => (e.before?.[f] ?? null) !== (e.after[f] ?? null) && !(f === "resolution_summary" && e.action === "resolve"),
        );
        const role = ROLE_LABEL[e.actor_role] ?? e.actor_role;
        const name = knownName(e.actor_sub);
        const evidence = e.after.evidence as { kind?: string } | undefined;
        return (
          <li key={e.id} className="relative text-sm">
            <span className="absolute top-1.5 -left-[1.3rem] h-2 w-2 rounded-full bg-slate-400" aria-hidden />
            <div className="flex flex-wrap items-baseline justify-between gap-x-3">
              <p>
                <span className="font-medium">{ACTION_LABEL[e.action] ?? e.action}</span>
                <span className="text-slate-600"> by {name ? `${name} (${role})` : `${role} ${e.actor_sub.slice(0, 8)}`}</span>
              </p>
              <time dateTime={e.ts} className="text-xs text-slate-500">
                {formatTime(e.ts)}
              </time>
            </div>
            {e.before !== null && changes.length > 0 && (
              <ul className="mt-1 space-y-0.5 text-xs text-slate-700">
                {changes.map((f) => (
                  <li key={f}>
                    {FIELD_LABEL[f]}: <span className="text-slate-500">{show(f, e.before?.[f])}</span> -&gt;{" "}
                    <span className="font-medium">{show(f, e.after[f])}</span>
                  </li>
                ))}
              </ul>
            )}
            {evidence?.kind && <p className="mt-1 text-xs text-slate-700">Photo: {evidence.kind}</p>}
            {e.note && (
              <p className="mt-1 rounded bg-slate-50 px-2 py-1 text-xs whitespace-pre-wrap text-slate-800">
                <span className="text-slate-500">{e.action === "resolve" ? "Summary" : "Reason"}: </span>
                {e.note}
              </p>
            )}
          </li>
        );
      })}
    </ol>
  );
}
