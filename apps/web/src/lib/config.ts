export const config = {
  apiUrl: (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, ""),
  userPoolId: process.env.NEXT_PUBLIC_USER_POOL_ID ?? "",
  clientId: process.env.NEXT_PUBLIC_CLIENT_ID ?? "",
  appEnv: process.env.NEXT_PUBLIC_APP_ENV ?? "prod",
};

export const DEFAULT_TENANT = "demo-campus";
