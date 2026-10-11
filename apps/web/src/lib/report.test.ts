import { describe, expect, it } from "vitest";
import { newIdempotencyKey } from "./api";
import { validateReport, type ReportForm } from "./report";

const base: ReportForm = { type: "blocked_drain", description: "Grate clogged", landmark: "Hostel B gate", coords: null };

describe("validateReport", () => {
  it("accepts a valid form and trims fields", () => {
    const { errors, body } = validateReport({ ...base, description: "  Grate clogged  ", landmark: " Gate " });
    expect(errors).toEqual({});
    expect(body).toEqual({ type: "blocked_drain", description: "Grate clogged", landmark: "Gate" });
  });

  it("requires a type", () => {
    expect(validateReport({ ...base, type: "" }).errors.type).toBeDefined();
  });

  it("enforces description length after trimming", () => {
    expect(validateReport({ ...base, description: "  ab  " }).errors.description).toMatch(/at least 3/);
    expect(validateReport({ ...base, description: "x".repeat(1001) }).errors.description).toMatch(/under 1000/);
    expect(validateReport({ ...base, description: "x".repeat(1000) }).body).not.toBeNull();
  });

  it("needs a location description or coordinates", () => {
    expect(validateReport({ ...base, landmark: "  " }).errors.landmark).toMatch(/use your location/);
    const { body } = validateReport({ ...base, landmark: "", coords: { lat: 12.9915512345, lng: 80.2336812345 } });
    expect(body).toEqual({ type: "blocked_drain", description: "Grate clogged", lat: 12.991551, lng: 80.233681 });
  });

  it("limits landmark length and rejects out of range coordinates", () => {
    expect(validateReport({ ...base, landmark: "x".repeat(201) }).errors.landmark).toMatch(/200/);
    expect(validateReport({ ...base, coords: { lat: 91, lng: 0 } }).errors.coords).toBeDefined();
  });

  it("does not send optional fields that are empty", () => {
    const { body } = validateReport(base);
    expect(body).not.toHaveProperty("lat");
    expect(body).not.toHaveProperty("lng");
  });
});

describe("newIdempotencyKey", () => {
  it("matches the server pattern and is unique", () => {
    const a = newIdempotencyKey();
    expect(a).toMatch(/^[A-Za-z0-9_-]{8,128}$/);
    expect(newIdempotencyKey()).not.toBe(a);
  });
});
