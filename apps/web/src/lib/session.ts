import type { Role } from "./types";

export interface Session {
  idToken: string;
  sub: string;
  email: string;
  role: Exclude<Role, "public">;
  tenantId: string;
  expiresAt: number;
}

const KEY = "dw.session";
let current: Session | null = null;
const listeners = new Set<() => void>();

export function decodeJwt(token: string): Record<string, unknown> {
  const part = token.split(".")[1];
  if (!part) throw new Error("malformed token");
  const b64 = part.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(part.length / 4) * 4, "=");
  const json = decodeURIComponent(
    Array.from(atob(b64), (c) => "%" + c.charCodeAt(0).toString(16).padStart(2, "0")).join(""),
  );
  return JSON.parse(json) as Record<string, unknown>;
}

export function sessionFromIdToken(idToken: string): Session {
  const claims = decodeJwt(idToken);
  const groups = Array.isArray(claims["cognito:groups"]) ? (claims["cognito:groups"] as string[]) : [];
  const role = groups.includes("operator") ? "operator" : groups.includes("field_worker") ? "field_worker" : null;
  if (!role) throw new Error("This account has no staff role.");
  const tenantId = claims["custom:tenant_id"];
  if (typeof tenantId !== "string" || !tenantId) throw new Error("This account has no tenant.");
  return {
    idToken,
    sub: String(claims.sub),
    email: typeof claims.email === "string" ? claims.email : String(claims.sub),
    role,
    tenantId,
    expiresAt: Number(claims.exp) * 1000,
  };
}

export function getSession(): Session | null {
  if (!current && typeof window !== "undefined") {
    try {
      const raw = window.sessionStorage.getItem(KEY);
      if (raw) current = JSON.parse(raw) as Session;
    } catch {
      current = null;
    }
  }
  if (current && current.expiresAt <= Date.now()) {
    clearSession();
    return null;
  }
  return current;
}

export function setSession(s: Session): void {
  current = s;
  try {
    window.sessionStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    // memory only
  }
  listeners.forEach((fn) => fn());
}

export function clearSession(): void {
  current = null;
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    // ignore
  }
  listeners.forEach((fn) => fn());
}

export function onSessionChange(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
