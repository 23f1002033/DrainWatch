export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const FALLBACK_CODES: Record<number, string> = {
  400: "BAD_REQUEST",
  401: "UNAUTHORIZED",
  403: "FORBIDDEN",
  404: "NOT_FOUND",
  409: "CONFLICT",
  413: "TOO_LARGE",
  422: "VALIDATION_ERROR",
  429: "RATE_LIMITED",
};

export function toApiError(status: number, body: unknown, headerRequestId: string | null = null): ApiError {
  const err = (body as { error?: { code?: unknown; message?: unknown; request_id?: unknown } } | null)?.error;
  const code =
    typeof err?.code === "string" ? err.code : (FALLBACK_CODES[status] ?? (status >= 500 ? "SERVER_ERROR" : "HTTP_ERROR"));
  const apiMessage =
    typeof err?.message === "string"
      ? err.message
      : typeof (body as { message?: unknown } | null)?.message === "string"
        ? (body as { message: string }).message
        : `HTTP ${status}`;
  const requestId = typeof err?.request_id === "string" ? err.request_id : headerRequestId;
  return new ApiError(status, code, apiMessage, requestId);
}

export function networkError(cause: unknown): ApiError {
  const detail = cause instanceof Error ? cause.message : String(cause);
  return new ApiError(0, "NETWORK", detail);
}

export function isConflict(err: unknown): boolean {
  return err instanceof ApiError && err.code === "VERSION_CONFLICT";
}

export function isRetryable(err: unknown): boolean {
  return err instanceof ApiError && (err.status === 0 || err.status === 429 || err.status >= 500);
}

export function userMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return "Something went wrong. Please try again.";
  switch (err.code) {
    case "NETWORK":
      return "Could not reach the server. Check your connection and try again.";
    case "RATE_LIMITED":
      return "Too many requests. Wait a few seconds and try again.";
    case "UNAUTHORIZED":
      return "Your session has expired. Sign in again.";
    case "FORBIDDEN":
      return `Not allowed: ${err.message}`;
    case "NOT_FOUND":
      return `Not found: ${err.message}`;
    case "VERSION_CONFLICT":
      return "This incident was updated by someone else. The latest version has been loaded.";
    case "ILLEGAL_TRANSITION":
      return `That action is no longer valid: ${err.message}`;
    case "IDEMPOTENCY_KEY_REUSED":
      return "This form was already submitted with different details. Start a new report.";
    case "VALIDATION_ERROR":
    case "BAD_REQUEST":
      return `Invalid request: ${err.message}`;
    default:
      return err.status >= 500 ? "The server had a problem. Please try again." : err.message;
  }
}
