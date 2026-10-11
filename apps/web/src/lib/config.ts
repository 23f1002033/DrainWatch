export const config = {
  apiUrl: (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, ""),
  userPoolId: process.env.NEXT_PUBLIC_USER_POOL_ID ?? "",
  clientId: process.env.NEXT_PUBLIC_CLIENT_ID ?? "",
  appEnv: process.env.NEXT_PUBLIC_APP_ENV ?? "prod",
};

export const DEFAULT_TENANT = "demo-campus";

const TENANT_NAMES: Record<string, string> = { "demo-campus": "Demo Campus" };

export function tenantName(id: string): string {
  return TENANT_NAMES[id] ?? id.split("-").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}
