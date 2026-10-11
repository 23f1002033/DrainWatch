"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Button, ErrorBox, Field, inputClass } from "@/components/ui";
import { api, newIdempotencyKey } from "@/lib/api";
import { DESCRIPTION_MAX, LANDMARK_MAX, TENANT_PATTERN, validateReport, type ReportErrors, type ReportForm } from "@/lib/report";
import { INCIDENT_TYPES, TYPE_LABEL } from "@/lib/types";

const EMPTY: ReportForm = { type: "", description: "", landmark: "", coords: null };

type Geo = { state: "idle" } | { state: "locating" } | { state: "error"; message: string };

export function ReportScreen() {
  const tenant = useSearchParams().get("t") ?? "";
  const [form, setForm] = useState<ReportForm>(EMPTY);
  const [errors, setErrors] = useState<ReportErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<unknown>(null);
  const [reference, setReference] = useState<string | null>(null);
  const [geo, setGeo] = useState<Geo>({ state: "idle" });
  const [accuracy, setAccuracy] = useState<number | null>(null);
  const idemKey = useRef<string>("");
  const [geoSupported, setGeoSupported] = useState(true);

  useEffect(() => setGeoSupported("geolocation" in navigator), []);

  if (!TENANT_PATTERN.test(tenant)) {
    return (
      <Shell>
        <ErrorBox message="This report link is missing its campus code. Scan the QR poster again." />
      </Shell>
    );
  }

  function update<K extends keyof ReportForm>(key: K, value: ReportForm[K]) {
    setForm((f) => ({ ...f, [key]: value }));
    setErrors((e) => ({ ...e, [key]: undefined, ...(key === "coords" ? { landmark: undefined } : {}) }));
  }

  function locate() {
    setGeo({ state: "locating" });
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        update("coords", { lat: pos.coords.latitude, lng: pos.coords.longitude });
        setAccuracy(Math.round(pos.coords.accuracy));
        setGeo({ state: "idle" });
      },
      (err) => {
        const message =
          err.code === err.PERMISSION_DENIED
            ? "Location permission was denied. Describe the location instead."
            : "Could not get your location. Describe the location instead.";
        setGeo({ state: "error", message });
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const { errors: found, body } = validateReport(form);
    setErrors(found);
    if (!body) {
      const first = Object.keys(found)[0];
      if (first) document.getElementById(first === "coords" ? "landmark" : first)?.focus();
      return;
    }
    if (!idemKey.current) idemKey.current = newIdempotencyKey();
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await api.report(tenant, body, idemKey.current);
      setReference(res.reference);
    } catch (err) {
      setSubmitError(err);
    } finally {
      setSubmitting(false);
    }
  }

  function reset() {
    idemKey.current = "";
    setForm(EMPTY);
    setErrors({});
    setReference(null);
    setSubmitError(null);
    setAccuracy(null);
    setGeo({ state: "idle" });
  }

  if (reference) {
    return (
      <Shell>
        <div className="rounded-lg border border-slate-200 bg-white p-5" role="status" aria-live="polite">
          <h2 className="text-lg font-semibold">Report received</h2>
          <p className="mt-1 text-sm text-slate-600">It is now in the facility team queue.</p>
          <p className="mt-4 text-sm text-slate-600">Your reference code</p>
          <p className="mt-1 font-mono text-2xl font-semibold tracking-wider" data-testid="reference">
            {reference}
          </p>
          <p className="mt-2 text-xs text-slate-500">Quote this code if you contact the facility team.</p>
          <Button className="mt-5 w-full" onClick={reset}>
            Report another problem
          </Button>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <form onSubmit={submit} noValidate className="space-y-5 rounded-lg border border-slate-200 bg-white p-4 sm:p-5">
        <fieldset aria-describedby={errors.type ? "type-error" : undefined}>
          <legend className="text-sm font-medium text-slate-800">What is the problem?</legend>
          <div className="mt-2 grid grid-cols-2 gap-2" id="type" tabIndex={-1}>
            {INCIDENT_TYPES.map((t) => (
              <label
                key={t}
                className={`flex min-h-12 cursor-pointer items-center gap-2 rounded-md border px-3 text-sm has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent ${
                  form.type === t ? "border-accent bg-blue-50 font-medium" : "border-slate-300"
                }`}
              >
                <input
                  type="radio"
                  name="type"
                  value={t}
                  checked={form.type === t}
                  onChange={() => update("type", t)}
                  className="accent-accent"
                />
                {TYPE_LABEL[t]}
              </label>
            ))}
          </div>
          {errors.type && (
            <p id="type-error" className="mt-1 text-xs text-red-700">
              {errors.type}
            </p>
          )}
        </fieldset>

        <Field label="Description" htmlFor="description" error={errors.description} hint="Depth, spread, anything near electricals.">
          <textarea
            id="description"
            rows={4}
            maxLength={DESCRIPTION_MAX}
            value={form.description}
            onChange={(e) => update("description", e.target.value)}
            aria-invalid={!!errors.description}
            aria-describedby={errors.description ? "description-error" : undefined}
            className={inputClass}
          />
        </Field>

        <Field label="Where is it?" htmlFor="landmark" error={errors.landmark} hint="Building, gate, road or nearby landmark.">
          <input
            id="landmark"
            type="text"
            maxLength={LANDMARK_MAX}
            value={form.landmark}
            onChange={(e) => update("landmark", e.target.value)}
            aria-invalid={!!errors.landmark}
            aria-describedby={errors.landmark ? "landmark-error" : undefined}
            className={inputClass}
          />
        </Field>

        <div className="space-y-2">
          {form.coords ? (
            <div className="flex items-center justify-between gap-2 rounded-md bg-slate-50 px-3 py-2 text-sm">
              <span>
                Location attached
                <span className="block font-mono text-xs text-slate-500">
                  {form.coords.lat.toFixed(5)}, {form.coords.lng.toFixed(5)}
                  {accuracy !== null && ` (within ${accuracy} m)`}
                </span>
              </span>
              <Button onClick={() => { update("coords", null); setAccuracy(null); }}>Remove</Button>
            </div>
          ) : (
            <>
              <Button
                className="w-full"
                onClick={locate}
                disabled={!geoSupported || geo.state === "locating"}
                title={geoSupported ? undefined : "This browser does not support location"}
              >
                {geo.state === "locating" ? "Getting location..." : "Use my location (optional)"}
              </Button>
              {!geoSupported && <p className="text-xs text-slate-500">Location is not available in this browser.</p>}
            </>
          )}
          {geo.state === "error" && <p className="text-xs text-red-700">{geo.message}</p>}
          {errors.coords && <p className="text-xs text-red-700">{errors.coords}</p>}
        </div>

        {submitError !== null && (
          <ErrorBox error={submitError}>
            <p className="mt-1 text-xs">Submitting again is safe; it will not create a duplicate report.</p>
          </ErrorBox>
        )}

        <Button type="submit" variant="primary" className="w-full" disabled={submitting}>
          {submitting ? "Sending..." : submitError ? "Try again" : "Send report"}
        </Button>
        <p className="text-xs text-slate-500">No account needed. Do not include personal information.</p>
      </form>
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-lg px-4 py-6">
      <header className="mb-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-accent">DrainWatch</p>
        <h1 className="text-xl font-semibold">Report waterlogging or a blocked drain</h1>
      </header>
      {children}
    </main>
  );
}
