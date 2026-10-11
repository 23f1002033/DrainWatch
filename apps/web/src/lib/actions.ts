import type { Session } from "./session";
import type { EvidenceKind, Incident, Status } from "./types";

export type ActionId = "triage" | "assign" | "start" | "resolve" | "close" | "verification_failed" | "reopen";

export interface ActionSpec {
  id: ActionId;
  label: string;
  to?: Status;
  textLabel: string | null;
  textRequired: boolean;
  variant: "primary" | "secondary" | "danger";
}

const SPECS: Record<ActionId, ActionSpec> = {
  triage: { id: "triage", label: "Triage", textLabel: "Reason", textRequired: true, variant: "primary" },
  assign: { id: "assign", label: "Assign", textLabel: "Reason", textRequired: true, variant: "primary" },
  start: { id: "start", label: "Start work", to: "in_progress", textLabel: null, textRequired: false, variant: "primary" },
  resolve: { id: "resolve", label: "Mark resolved", to: "resolved", textLabel: "Resolution summary", textRequired: true, variant: "primary" },
  close: { id: "close", label: "Verify and close", to: "closed", textLabel: "Note (optional)", textRequired: false, variant: "primary" },
  verification_failed: {
    id: "verification_failed",
    label: "Verification failed",
    to: "in_progress",
    textLabel: "What still needs fixing",
    textRequired: true,
    variant: "danger",
  },
  reopen: { id: "reopen", label: "Reopen", to: "triaged", textLabel: "Reason for reopening", textRequired: true, variant: "danger" },
};

export function availableActions(incident: Incident, session: Session): ActionSpec[] {
  const s = incident.status;
  const ids: ActionId[] = [];
  if (session.role === "operator") {
    if (s === "reported" || s === "triaged") ids.push("triage");
    if (s === "triaged" || s === "assigned") ids.push("assign");
    if (s === "resolved") ids.push("close", "verification_failed");
    if (s === "closed") ids.push("reopen");
  } else if (incident.assigned_to === session.sub) {
    if (s === "assigned") ids.push("start");
    if (s === "in_progress") ids.push("resolve");
  }
  return ids.map((id) => SPECS[id]);
}

export function noActionReason(incident: Incident, session: Session, assigneeName: string): string {
  if (session.role === "field_worker") {
    if (incident.assigned_to !== session.sub) {
      return incident.assigned_to ? `Assigned to ${assigneeName}. Only the assignee can update it.` : "Not assigned to you yet.";
    }
    if (incident.status === "resolved") return "Waiting for an operator to verify your fix.";
    if (incident.status === "closed") return "Closed.";
    return "No field actions in this status.";
  }
  if (incident.status === "assigned") return `Waiting for ${assigneeName} to start work.`;
  if (incident.status === "in_progress") return `${assigneeName} is working on it. You can verify once it is resolved.`;
  return "No actions available in this status.";
}

const EVIDENCE_STATUSES: Record<EvidenceKind, Status[]> = {
  before: ["assigned", "in_progress"],
  after: ["in_progress", "resolved"],
};

export function evidenceKinds(incident: Incident, session: Session): EvidenceKind[] {
  if (session.role === "field_worker" && incident.assigned_to !== session.sub) return [];
  return (["before", "after"] as const).filter((k) => EVIDENCE_STATUSES[k].includes(incident.status));
}
