import { describe, expect, it } from "vitest";
import { keepEvidenceUrls, needsUrlRefresh, refreshDelayMs } from "./evidence";
import type { Evidence, Incident } from "./types";

const ev = (key: string, url?: string): Evidence => ({ key, kind: "before", by: "u", ts: "t", ...(url ? { url, url_expires_in: 300 } : {}) });
const inc = (evidence: Evidence[]): Incident => ({
  id: "I",
  reference: "DW-1",
  type: "waterlogging",
  description: "d",
  status: "in_progress",
  version: 2,
  created_at: "t",
  updated_at: "t",
  landmark: null,
  lat: null,
  lng: null,
  severity: "S2",
  assigned_to: "u",
  resolution_summary: null,
  evidence,
});

describe("keepEvidenceUrls", () => {
  it("copies known urls onto a mutation response that has none", () => {
    const out = keepEvidenceUrls(inc([ev("a"), ev("b")]), inc([ev("a", "https://s3/a")]));
    expect(out.evidence.map((e) => e.url)).toEqual(["https://s3/a", undefined]);
    expect(needsUrlRefresh(out)).toBe(true);
  });

  it("prefers urls from the new response", () => {
    const out = keepEvidenceUrls(inc([ev("a", "https://s3/new")]), inc([ev("a", "https://s3/old")]));
    expect(out.evidence[0]!.url).toBe("https://s3/new");
    expect(needsUrlRefresh(out)).toBe(false);
  });
});

describe("refreshDelayMs", () => {
  it("refreshes 30 s before the shortest expiry", () => {
    expect(refreshDelayMs(inc([ev("a", "u")]))).toBe(270_000);
  });

  it("does nothing without urls", () => {
    expect(refreshDelayMs(inc([]))).toBeNull();
    expect(refreshDelayMs(inc([ev("a")]))).toBeNull();
  });
});
