export type Status = "reported" | "triaged" | "assigned" | "in_progress" | "resolved" | "closed";
export type Severity = "S1" | "S2" | "S3";
export type IncidentType = "waterlogging" | "blocked_drain";
export type Role = "operator" | "field_worker" | "public";
export type EvidenceKind = "before" | "after";

export const STATUSES: Status[] = ["reported", "triaged", "assigned", "in_progress", "resolved", "closed"];
export const SEVERITIES: Severity[] = ["S1", "S2", "S3"];
export const INCIDENT_TYPES: IncidentType[] = ["waterlogging", "blocked_drain"];

export const STATUS_LABEL: Record<Status, string> = {
  reported: "Reported",
  triaged: "Triaged",
  assigned: "Assigned",
  in_progress: "In progress",
  resolved: "Resolved",
  closed: "Closed",
};

export const TYPE_LABEL: Record<IncidentType, string> = {
  waterlogging: "Waterlogging",
  blocked_drain: "Blocked drain",
};

export const SEVERITY_HELP: Record<Severity, string> = {
  S1: "Blocks access or near electricals",
  S2: "Ponding or spreading",
  S3: "Minor",
};

export interface Evidence {
  key: string;
  kind: EvidenceKind;
  by: string;
  ts: string;
  url?: string;
  url_expires_in?: number;
}

export interface Incident {
  id: string;
  reference: string;
  type: IncidentType;
  description: string;
  status: Status;
  version: number;
  created_at: string;
  updated_at: string;
  landmark: string | null;
  lat: number | null;
  lng: number | null;
  severity: Severity | null;
  assigned_to: string | null;
  resolution_summary: string | null;
  evidence: Evidence[];
}

export interface IncidentEvent {
  incident_id: string;
  id: string;
  actor_sub: string;
  actor_role: Role;
  action: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown>;
  ts: string;
  note: string | null;
}

export interface Member {
  id: string;
  name: string;
  role: Exclude<Role, "public">;
}

export interface PublicReport {
  type: IncidentType;
  description: string;
  landmark?: string;
  lat?: number;
  lng?: number;
}

export interface QueueQuery {
  status?: Status;
  severity?: Severity;
  type?: IncidentType;
  older_than_hours?: number;
  cursor?: string;
  limit?: number;
}

export interface UploadTicket {
  key: string;
  url: string;
  method: "POST";
  fields: Record<string, string>;
  max_bytes: number;
  expires_in: number;
}
