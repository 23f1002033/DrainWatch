import type { Incident, Severity, Status } from "./types";

const HOUR = 3600_000;

// Response targets, measured from the time the incident was reported.
export const OVERDUE_RULES = {
  triageWithinHours: 1,
  resolveWithinHours: { S1: 4, S2: 24, S3: 72 } as Record<Severity, number>,
};

const UNRESOLVED: Status[] = ["triaged", "assigned", "in_progress"];

export function overdueDeadline(i: Incident): number | null {
  const created = new Date(i.created_at).getTime();
  if (Number.isNaN(created)) return null;
  if (i.status === "reported") return created + OVERDUE_RULES.triageWithinHours * HOUR;
  if (i.severity && UNRESOLVED.includes(i.status)) return created + OVERDUE_RULES.resolveWithinHours[i.severity] * HOUR;
  return null;
}

export function isOverdue(i: Incident, now: number = Date.now()): boolean {
  const deadline = overdueDeadline(i);
  return deadline !== null && now > deadline;
}

const SEVERITY_RANK: Record<Severity, number> = { S1: 0, S2: 1, S3: 2 };

export function compareIncidents(a: Incident, b: Incident): number {
  const reported = Number(b.status === "reported") - Number(a.status === "reported");
  if (reported !== 0) return reported;
  const sev = (a.severity ? SEVERITY_RANK[a.severity] : 3) - (b.severity ? SEVERITY_RANK[b.severity] : 3);
  if (sev !== 0) return sev;
  return a.created_at < b.created_at ? -1 : a.created_at > b.created_at ? 1 : 0;
}

export function sortIncidents(items: Incident[]): Incident[] {
  return [...items].sort(compareIncidents);
}

export type QuickViewId = "open" | "triage" | "unassigned" | "in_progress" | "verification" | "overdue" | "all";

export const QUICK_VIEWS: { id: QuickViewId; label: string; match: (i: Incident, now: number) => boolean }[] = [
  { id: "open", label: "Open", match: (i) => i.status !== "closed" },
  { id: "triage", label: "Needs triage", match: (i) => i.status === "reported" },
  { id: "unassigned", label: "Unassigned", match: (i) => i.status === "triaged" },
  { id: "in_progress", label: "In progress", match: (i) => i.status === "assigned" || i.status === "in_progress" },
  { id: "verification", label: "Awaiting verification", match: (i) => i.status === "resolved" },
  { id: "overdue", label: "Overdue", match: (i, now) => isOverdue(i, now) },
  { id: "all", label: "All", match: () => true },
];

export function quickViewCounts(items: Incident[], now: number = Date.now()): Record<QuickViewId, number> {
  const counts = Object.fromEntries(QUICK_VIEWS.map((v) => [v.id, 0])) as Record<QuickViewId, number>;
  for (const i of items) for (const v of QUICK_VIEWS) if (v.match(i, now)) counts[v.id] += 1;
  return counts;
}

export function applyQuickView(items: Incident[], id: QuickViewId, now: number = Date.now()): Incident[] {
  const view = QUICK_VIEWS.find((v) => v.id === id) ?? QUICK_VIEWS[0]!;
  return sortIncidents(items.filter((i) => view.match(i, now)));
}
