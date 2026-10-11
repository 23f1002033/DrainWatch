import { config } from "./config";
import { ApiError, networkError, toApiError } from "./errors";
import { clearSession, getSession } from "./session";
import type {
  EvidenceKind,
  Incident,
  IncidentEvent,
  PublicReport,
  QueueQuery,
  Severity,
  Status,
  UploadTicket,
  Worker,
} from "./types";

type Fetch = typeof fetch;

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  headers?: Record<string, string>;
  auth?: boolean;
}

export async function request<T>(path: string, opts: RequestOptions = {}, fetchImpl: Fetch = fetch): Promise<T> {
  const headers: Record<string, string> = { ...opts.headers };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.auth !== false) {
    const session = getSession();
    if (!session) throw new ApiError(401, "UNAUTHORIZED", "not signed in");
    headers.Authorization = `Bearer ${session.idToken}`;
  }
  let res: Response;
  try {
    res = await fetchImpl(`${config.apiUrl}${path}`, {
      method: opts.method ?? "GET",
      headers,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    });
  } catch (cause) {
    throw networkError(cause);
  }
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!res.ok) {
    const err = toApiError(res.status, data, res.headers.get("x-request-id"));
    if (err.status === 401 && opts.auth !== false) clearSession();
    throw err;
  }
  return data as T;
}

export function newIdempotencyKey(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export const api = {
  report(tenant: string, body: PublicReport, idempotencyKey: string, fetchImpl?: Fetch) {
    return request<{ reference: string }>(
      `/api/v1/public/${encodeURIComponent(tenant)}/incidents`,
      { method: "POST", body, auth: false, headers: { "Idempotency-Key": idempotencyKey } },
      fetchImpl,
    );
  },
  queue(q: QueueQuery) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(q)) if (v !== undefined && v !== "") params.set(k, String(v));
    const qs = params.toString();
    return request<{ items: Incident[]; next_cursor: string | null }>(`/api/v1/incidents${qs ? `?${qs}` : ""}`);
  },
  get(id: string) {
    return request<Incident>(`/api/v1/incidents/${encodeURIComponent(id)}`);
  },
  events(id: string) {
    return request<{ items: IncidentEvent[] }>(`/api/v1/incidents/${encodeURIComponent(id)}/events`);
  },
  workers() {
    return request<{ items: Worker[] }>(`/api/v1/workers`);
  },
  triage(id: string, expected_version: number, severity: Severity, reason: string) {
    return request<Incident>(`/api/v1/incidents/${encodeURIComponent(id)}/triage`, {
      method: "POST",
      body: { severity, reason, expected_version },
    });
  },
  assign(id: string, expected_version: number, worker_id: string, reason: string) {
    return request<Incident>(`/api/v1/incidents/${encodeURIComponent(id)}/assignments`, {
      method: "POST",
      body: { worker_id, reason, expected_version },
    });
  },
  transition(id: string, expected_version: number, to: Status, note?: string) {
    return request<Incident>(`/api/v1/incidents/${encodeURIComponent(id)}/transitions`, {
      method: "POST",
      body: note ? { to, note, expected_version } : { to, expected_version },
    });
  },
  uploadTicket(id: string, content_type: string) {
    return request<UploadTicket>(`/api/v1/incidents/${encodeURIComponent(id)}/uploads`, {
      method: "POST",
      body: { content_type },
    });
  },
  addEvidence(id: string, key: string, kind: EvidenceKind) {
    return request<Incident>(`/api/v1/incidents/${encodeURIComponent(id)}/evidence`, {
      method: "POST",
      body: { key, kind },
    });
  },
};

export async function uploadToS3(ticket: UploadTicket, blob: Blob, fetchImpl: Fetch = fetch): Promise<void> {
  if (blob.size > ticket.max_bytes) throw new ApiError(413, "TOO_LARGE", "image is larger than 5 MB after resizing");
  const form = new FormData();
  for (const [k, v] of Object.entries(ticket.fields)) form.append(k, v);
  form.append("file", blob);
  let res: Response;
  try {
    res = await fetchImpl(ticket.url, { method: "POST", body: form });
  } catch (cause) {
    throw networkError(cause);
  }
  if (!res.ok) throw new ApiError(res.status, "UPLOAD_FAILED", `storage rejected the upload (HTTP ${res.status})`);
}
