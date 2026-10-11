"use client";

import { useEffect, useRef, useState } from "react";
import { Button, ErrorBox } from "@/components/ui";
import { api, uploadToS3 } from "@/lib/api";
import { isConflict } from "@/lib/errors";
import { formatTime } from "@/lib/format";
import { toUploadJpeg } from "@/lib/image";
import type { Evidence, EvidenceKind, Incident } from "@/lib/types";

type Step = "idle" | "resizing" | "uploading" | "recording";
const STEP_LABEL: Record<Step, string> = { idle: "", resizing: "Resizing...", uploading: "Uploading...", recording: "Saving..." };

export function EvidencePanel({
  incident,
  kinds,
  nameOf,
  onAdded,
  onConflict,
  onUrlsExpired,
}: {
  incident: Incident;
  kinds: EvidenceKind[];
  nameOf: (sub: string | null) => string;
  onAdded: (next: Incident) => void;
  onConflict: () => void;
  onUrlsExpired: () => Promise<void>;
}) {
  const [kind, setKind] = useState<EvidenceKind | "">("");
  const [step, setStep] = useState<Step>("idle");
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState<Blob | null>(null);
  const [resizeError, setResizeError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (kind && !kinds.includes(kind)) setKind("");
    if (!kind && kinds.length === 1) setKind(kinds[0]!);
  }, [kinds, kind]);

  async function upload(blob: Blob, k: EvidenceKind) {
    setError(null);
    try {
      setStep("uploading");
      const ticket = await api.uploadTicket(incident.id, "image/jpeg");
      await uploadToS3(ticket, blob);
      setStep("recording");
      const next = await api.addEvidence(incident.id, ticket.key, k);
      setPending(null);
      if (fileRef.current) fileRef.current.value = "";
      onAdded(next);
    } catch (e) {
      setError(e);
      if (isConflict(e)) onConflict();
    } finally {
      setStep("idle");
    }
  }

  async function onFile(file: File | undefined) {
    if (!file || !kind) return;
    setError(null);
    setStep("resizing");
    let blob: Blob;
    try {
      blob = await toUploadJpeg(file);
    } catch {
      setStep("idle");
      setPending(null);
      setResizeError("Could not read that image. Try a JPEG or PNG photo.");
      return;
    }
    setResizeError(null);
    setPending(blob);
    await upload(blob, kind);
  }

  const busy = step !== "idle";

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="text-sm font-semibold">Photos</h2>
      {incident.evidence.length === 0 ? (
        <p className="mt-2 text-sm text-slate-500">No photos yet.</p>
      ) : (
        <ul className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {incident.evidence.map((ev) => (
            <li key={ev.key} className="overflow-hidden rounded-md border border-slate-200">
              <Thumb evidence={ev} reference={incident.reference} onExpired={onUrlsExpired} />
              <div className="px-2 py-1.5 text-xs">
                <span className="font-medium capitalize">{ev.kind}</span>
                <span className="block text-slate-500">
                  {nameOf(ev.by)}, {formatTime(ev.ts)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 border-t border-slate-100 pt-3">
        {kinds.length === 0 ? (
          <p className="text-xs text-slate-500">
            {incident.status === "reported" || incident.status === "triaged"
              ? "Photos can be added once the incident is assigned."
              : incident.status === "closed"
                ? "Closed incidents do not accept photos."
                : "Only the assigned field worker or an operator can add photos."}
          </p>
        ) : (
          <div className="space-y-2">
            <fieldset className="flex flex-wrap items-center gap-3 text-sm">
              <legend className="sr-only">Photo type</legend>
              {kinds.map((k) => (
                <label key={k} className="flex items-center gap-1.5">
                  <input type="radio" name="evidence-kind" value={k} checked={kind === k} onChange={() => setKind(k)} disabled={busy} />
                  {k === "before" ? "Before work" : "After work"}
                </label>
              ))}
            </fieldset>
            <label
              htmlFor="photo"
              className={`flex min-h-11 items-center justify-center rounded-md border border-dashed px-3 text-sm ${
                !kind || busy ? "cursor-not-allowed border-slate-200 text-slate-400" : "cursor-pointer border-slate-400 text-slate-800 hover:bg-slate-50"
              } has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-accent`}
            >
              {busy ? STEP_LABEL[step] : kind ? "Take or choose a photo" : "Choose before or after first"}
              <input
                ref={fileRef}
                id="photo"
                type="file"
                accept="image/jpeg,image/png,image/webp,image/heic,image/*"
                className="sr-only"
                disabled={!kind || busy}
                onChange={(e) => void onFile(e.target.files?.[0])}
              />
            </label>
            <p className="text-xs text-slate-500">Resized to 1600 px and re-encoded on this device; location data is removed.</p>
            {resizeError && <ErrorBox message={resizeError} />}
            {error !== null && (
              <ErrorBox error={error} onRetry={pending && kind && !isConflict(error) ? () => void upload(pending, kind) : undefined} />
            )}
          </div>
        )}
      </div>
    </section>
  );
}

type ThumbState = "loading" | "loaded" | "refreshing" | "failed";

function Thumb({ evidence, reference, onExpired }: { evidence: Evidence; reference: string; onExpired: () => Promise<void> }) {
  const [state, setState] = useState<ThumbState>("loading");
  const [attempt, setAttempt] = useState(0);
  const retried = useRef(false);
  const label = `${evidence.kind === "before" ? "Before" : "After"} photo for ${reference}`;

  async function refetch() {
    setState("refreshing");
    try {
      await onExpired();
      setAttempt((n) => n + 1);
      setState("loading");
    } catch {
      setState("failed");
    }
  }

  function onError() {
    // A failed load usually means the presigned URL expired: refetch the detail once, then give up.
    if (retried.current) {
      setState("failed");
      return;
    }
    retried.current = true;
    void refetch();
  }

  const box = "flex aspect-[4/3] w-full items-center justify-center bg-slate-100 px-2 text-center text-xs text-slate-500";

  if (state === "failed") {
    return (
      <div className={`${box} flex-col gap-1.5`} role="alert">
        Could not load this photo.
        <Button
          className="min-h-8 text-xs"
          onClick={() => {
            retried.current = true;
            void refetch();
          }}
        >
          Retry
        </Button>
      </div>
    );
  }
  if (!evidence.url) return <div className={box}>Loading photo...</div>;

  return (
    <a href={evidence.url} target="_blank" rel="noreferrer" className="relative block bg-slate-100" title="Open full size in a new tab">
      <img
        key={`${evidence.url}#${attempt}`}
        src={evidence.url}
        alt={label}
        loading="lazy"
        onLoad={() => {
          retried.current = false;
          setState("loaded");
        }}
        onError={onError}
        className={`aspect-[4/3] w-full object-cover ${state === "loaded" ? "" : "opacity-0"}`}
      />
      {state !== "loaded" && <span className={`${box} absolute inset-0`}>Loading photo...</span>}
      <span className="sr-only">(opens full size in a new tab)</span>
    </a>
  );
}
