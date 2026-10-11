import { describe, expect, it } from "vitest";
import { applyQuickView, compareIncidents, isOverdue, OVERDUE_RULES, quickViewCounts, sortIncidents } from "./queue";
import type { Incident, Severity, Status } from "./types";

const NOW = Date.parse("2026-10-11T12:00:00.000Z");
const hoursAgo = (h: number) => new Date(NOW - h * 3600_000).toISOString();

let n = 0;
function inc(status: Status, severity: Severity | null, ageHours: number): Incident {
  n += 1;
  return {
    id: `ID${n}`,
    reference: `DW-${n}`,
    type: "waterlogging",
    description: "d",
    status,
    version: 1,
    created_at: hoursAgo(ageHours),
    updated_at: hoursAgo(ageHours),
    landmark: null,
    lat: null,
    lng: null,
    severity,
    assigned_to: null,
    resolution_summary: null,
    evidence: [],
  };
}

describe("overdue rules", () => {
  it("uses the configured targets", () => {
    expect(OVERDUE_RULES).toEqual({ triageWithinHours: 1, resolveWithinHours: { S1: 4, S2: 24, S3: 72 } });
  });

  it("flags reported incidents not triaged within 1 hour", () => {
    expect(isOverdue(inc("reported", null, 0.9), NOW)).toBe(false);
    expect(isOverdue(inc("reported", null, 1.1), NOW)).toBe(true);
  });

  it.each([
    ["S1", 3.9, 4.1],
    ["S2", 23.9, 24.1],
    ["S3", 71.9, 72.1],
  ] as const)("flags %s not resolved in time", (sev, inside, outside) => {
    for (const status of ["triaged", "assigned", "in_progress"] as const) {
      expect(isOverdue(inc(status, sev, inside), NOW)).toBe(false);
      expect(isOverdue(inc(status, sev, outside), NOW)).toBe(true);
    }
  });

  it("never flags resolved or closed incidents", () => {
    expect(isOverdue(inc("resolved", "S1", 100), NOW)).toBe(false);
    expect(isOverdue(inc("closed", "S1", 100), NOW)).toBe(false);
  });
});

describe("sort", () => {
  it("puts reported first, then S1 > S2 > S3, then oldest first", () => {
    const items = [
      inc("assigned", "S3", 10),
      inc("triaged", "S1", 1),
      inc("reported", null, 2),
      inc("in_progress", "S1", 5),
      inc("triaged", "S2", 3),
      inc("reported", null, 8),
      inc("resolved", null, 50),
    ];
    const order = sortIncidents(items).map((i) => `${i.status}:${i.severity ?? "-"}:${Math.round((NOW - Date.parse(i.created_at)) / 3600_000)}`);
    expect(order).toEqual([
      "reported:-:8",
      "reported:-:2",
      "in_progress:S1:5",
      "triaged:S1:1",
      "triaged:S2:3",
      "assigned:S3:10",
      "resolved:-:50",
    ]);
  });

  it("is stable for equal keys", () => {
    const a = inc("triaged", "S2", 3);
    expect(compareIncidents(a, { ...a, id: "other" })).toBe(0);
  });
});

describe("quick views", () => {
  const items = [
    inc("reported", null, 2),
    inc("triaged", "S2", 1),
    inc("assigned", "S1", 5),
    inc("in_progress", "S3", 1),
    inc("resolved", "S2", 30),
    inc("closed", "S2", 40),
  ];

  it("counts each view from loaded data", () => {
    expect(quickViewCounts(items, NOW)).toEqual({
      open: 5,
      triage: 1,
      unassigned: 1,
      in_progress: 2,
      verification: 1,
      overdue: 2,
      all: 6,
    });
  });

  it("filters and sorts", () => {
    expect(applyQuickView(items, "open", NOW).map((i) => i.status)).toEqual(["reported", "assigned", "resolved", "triaged", "in_progress"]);
    expect(applyQuickView(items, "overdue", NOW).map((i) => i.status)).toEqual(["reported", "assigned"]);
  });
});
