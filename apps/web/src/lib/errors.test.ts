import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, request } from "./api";
import { ApiError, isConflict, isRetryable, toApiError, userMessage } from "./errors";
import { getSession, setSession } from "./session";

function res(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(body === undefined ? "" : typeof body === "string" ? body : JSON.stringify(body), { status, headers });
}

const session = {
  idToken: "a.b.c",
  sub: "sub-1",
  email: "op@example.com",
  role: "operator" as const,
  tenantId: "demo-campus",
  expiresAt: Date.now() + 3600_000,
};

describe("toApiError", () => {
  it("reads the API error envelope", () => {
    const err = toApiError(409, { error: { code: "VERSION_CONFLICT", message: "expected version 2, current is 3", request_id: "r1" } });
    expect(err).toMatchObject({ status: 409, code: "VERSION_CONFLICT", message: "expected version 2, current is 3", requestId: "r1" });
  });

  it("falls back to a code from the status when the body is not the envelope", () => {
    expect(toApiError(401, { message: "Unauthorized" })).toMatchObject({ code: "UNAUTHORIZED", message: "Unauthorized" });
    expect(toApiError(429, null).code).toBe("RATE_LIMITED");
    expect(toApiError(502, "<html>").code).toBe("SERVER_ERROR");
  });

  it("uses the header request id when the body has none", () => {
    expect(toApiError(500, null, "hdr-1").requestId).toBe("hdr-1");
  });
});

describe("userMessage", () => {
  it.each([
    ["VERSION_CONFLICT", 409, /updated by someone else/],
    ["ILLEGAL_TRANSITION", 409, /no longer valid/],
    ["IDEMPOTENCY_KEY_REUSED", 409, /already submitted/],
    ["NETWORK", 0, /Could not reach the server/],
    ["UNAUTHORIZED", 401, /Sign in again/],
    ["SERVER_ERROR", 503, /server had a problem/],
  ])("maps %s", (code, status, pattern) => {
    expect(userMessage(new ApiError(status, code, "detail"))).toMatch(pattern);
  });

  it("includes the server detail for validation errors", () => {
    expect(userMessage(new ApiError(422, "VALIDATION_ERROR", "description: too short"))).toBe("Invalid request: description: too short");
  });

  it("classifies retryable and conflict errors", () => {
    expect(isRetryable(new ApiError(0, "NETWORK", "x"))).toBe(true);
    expect(isRetryable(new ApiError(503, "SERVER_ERROR", "x"))).toBe(true);
    expect(isRetryable(new ApiError(422, "VALIDATION_ERROR", "x"))).toBe(false);
    expect(isConflict(new ApiError(409, "VERSION_CONFLICT", "x"))).toBe(true);
    expect(isConflict(new ApiError(409, "ILLEGAL_TRANSITION", "x"))).toBe(false);
  });
});

describe("request", () => {
  beforeEach(() => {
    sessionStorage.clear();
    setSession(session);
  });

  it("sends the ID token as a Bearer token and parses JSON", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(res(200, { ok: 1 }));
    await expect(request("/x", {}, fetchImpl)).resolves.toEqual({ ok: 1 });
    expect(fetchImpl.mock.calls[0]![1].headers.Authorization).toBe("Bearer a.b.c");
  });

  it("maps network failures to NETWORK", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(request("/x", {}, fetchImpl)).rejects.toMatchObject({ status: 0, code: "NETWORK" });
  });

  it("clears the session on 401", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(res(401, { message: "Unauthorized" }));
    await expect(request("/x", {}, fetchImpl)).rejects.toMatchObject({ code: "UNAUTHORIZED" });
    expect(getSession()).toBeNull();
  });

  it("maps a 409 envelope to VERSION_CONFLICT", async () => {
    const body = { error: { code: "VERSION_CONFLICT", message: "incident was changed by another request", request_id: "q" } };
    const fetchImpl = vi.fn().mockResolvedValue(res(409, body));
    await expect(request("/x", { method: "POST", body: {} }, fetchImpl)).rejects.toMatchObject({ code: "VERSION_CONFLICT" });
  });

  it("does not require a session for the public report and sends the Idempotency-Key", async () => {
    sessionStorage.clear();
    const fetchImpl = vi.fn().mockResolvedValue(res(201, { reference: "DW-ABC" }));
    await expect(api.report("demo-campus", { type: "waterlogging", description: "abc" }, "key-12345678", fetchImpl)).resolves.toEqual({
      reference: "DW-ABC",
    });
    const init = fetchImpl.mock.calls[0]![1];
    expect(init.headers["Idempotency-Key"]).toBe("key-12345678");
    expect(init.headers.Authorization).toBeUndefined();
  });
});
