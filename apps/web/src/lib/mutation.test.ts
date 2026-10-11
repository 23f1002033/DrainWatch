import { describe, expect, it, vi } from "vitest";
import { availableActions, evidenceKinds } from "./actions";
import { ApiError } from "./errors";
import { fitWithin } from "./image";
import { mutate } from "./mutation";
import type { Session } from "./session";
import type { Incident, Status } from "./types";

const incident = (status: Status, assigned_to: string | null = null): Incident => ({
  id: "01J00000000000000000000000",
  reference: "DW-1",
  type: "waterlogging",
  description: "d",
  status,
  version: 4,
  created_at: "2026-10-11T00:00:00.000Z",
  updated_at: "2026-10-11T00:00:00.000Z",
  landmark: null,
  lat: null,
  lng: null,
  severity: null,
  assigned_to,
  resolution_summary: null,
  evidence: [],
});

const op: Session = { idToken: "t", sub: "op", email: "o", role: "operator", tenantId: "t", expiresAt: 0 };
const fw: Session = { ...op, sub: "ravi", role: "field_worker" };

describe("mutate", () => {
  it("returns the updated incident without reloading", async () => {
    const reload = vi.fn();
    const out = await mutate(async () => incident("triaged"), reload);
    expect(out).toMatchObject({ kind: "ok" });
    expect(reload).not.toHaveBeenCalled();
  });

  it("reloads and reports a conflict on VERSION_CONFLICT", async () => {
    const reload = vi.fn().mockResolvedValue(undefined);
    const out = await mutate(() => Promise.reject(new ApiError(409, "VERSION_CONFLICT", "expected version 4, current is 5")), reload);
    expect(out).toEqual({ kind: "conflict", reloadError: null });
    expect(reload).toHaveBeenCalledOnce();
  });

  it("surfaces a failed reload after a conflict", async () => {
    const reloadErr = new ApiError(0, "NETWORK", "offline");
    const out = await mutate(() => Promise.reject(new ApiError(409, "VERSION_CONFLICT", "x")), () => Promise.reject(reloadErr));
    expect(out).toEqual({ kind: "conflict", reloadError: reloadErr });
  });

  it("does not reload on other errors", async () => {
    const reload = vi.fn();
    const err = new ApiError(409, "ILLEGAL_TRANSITION", "cannot move");
    expect(await mutate(() => Promise.reject(err), reload)).toEqual({ kind: "error", error: err });
    expect(reload).not.toHaveBeenCalled();
  });
});

describe("availableActions", () => {
  const ids = (i: Incident, s: Session) => availableActions(i, s).map((a) => a.id);

  it("matches the operator lifecycle", () => {
    expect(ids(incident("reported"), op)).toEqual(["triage"]);
    expect(ids(incident("triaged"), op)).toEqual(["triage", "assign"]);
    expect(ids(incident("assigned", "ravi"), op)).toEqual(["assign"]);
    expect(ids(incident("in_progress", "ravi"), op)).toEqual([]);
    expect(ids(incident("resolved", "ravi"), op)).toEqual(["close", "verification_failed"]);
    expect(ids(incident("closed"), op)).toEqual(["reopen"]);
  });

  it("only lets the assigned field worker start and resolve", () => {
    expect(ids(incident("assigned", "ravi"), fw)).toEqual(["start"]);
    expect(ids(incident("in_progress", "ravi"), fw)).toEqual(["resolve"]);
    expect(ids(incident("assigned", "someone"), fw)).toEqual([]);
    expect(ids(incident("resolved", "ravi"), fw)).toEqual([]);
  });

  it("requires text where the server requires a reason", () => {
    const required = (i: Incident, s: Session) => availableActions(i, s).filter((a) => a.textRequired).map((a) => a.id);
    expect(required(incident("triaged"), op)).toEqual(["triage", "assign"]);
    expect(required(incident("resolved"), op)).toEqual(["verification_failed"]);
    expect(required(incident("closed"), op)).toEqual(["reopen"]);
    expect(required(incident("in_progress", "ravi"), fw)).toEqual(["resolve"]);
  });

  it("allows evidence kinds by status and assignee", () => {
    expect(evidenceKinds(incident("assigned", "ravi"), fw)).toEqual(["before"]);
    expect(evidenceKinds(incident("in_progress", "ravi"), fw)).toEqual(["before", "after"]);
    expect(evidenceKinds(incident("in_progress", "other"), fw)).toEqual([]);
    expect(evidenceKinds(incident("resolved", "ravi"), op)).toEqual(["after"]);
    expect(evidenceKinds(incident("closed"), op)).toEqual([]);
  });
});

describe("fitWithin", () => {
  it("scales the long edge to 1600 and never upscales", () => {
    expect(fitWithin(3000, 2000)).toEqual({ width: 1600, height: 1067 });
    expect(fitWithin(1200, 4000)).toEqual({ width: 480, height: 1600 });
    expect(fitWithin(800, 600)).toEqual({ width: 800, height: 600 });
  });
});
