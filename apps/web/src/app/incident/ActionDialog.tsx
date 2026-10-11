"use client";

import { useEffect, useState } from "react";
import { Dialog } from "@/components/Dialog";
import { Button, ErrorBox, Field, inputClass } from "@/components/ui";
import { api } from "@/lib/api";
import type { ActionSpec } from "@/lib/actions";
import { mutate } from "@/lib/mutation";
import { SEVERITIES, SEVERITY_HELP, type Incident, type Severity, type Member } from "@/lib/types";

const TEXT_MAX = { triage: 1000, assign: 1000 } as Record<string, number>;

export function ActionDialog({
  action,
  incident,
  workers,
  onClose,
  onApplied,
  onConflict,
  reload,
}: {
  action: ActionSpec | null;
  incident: Incident;
  workers: Member[];
  onClose: () => void;
  onApplied: (next: Incident, label: string) => void;
  onConflict: () => void;
  reload: () => Promise<void>;
}) {
  const [text, setText] = useState("");
  const [severity, setSeverity] = useState<Severity | "">("");
  const [workerId, setWorkerId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);

  useEffect(() => {
    if (!action) return;
    setText("");
    setSeverity(incident.severity ?? "");
    setWorkerId(incident.assigned_to ?? "");
    setError(null);
    setFieldError(null);
  }, [action, incident.severity, incident.assigned_to]);

  if (!action) return <Dialog open={false} title="" onClose={onClose}>{null}</Dialog>;
  const spec = action;
  const max = TEXT_MAX[spec.id] ?? 2000;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const note = text.trim();
    if (spec.id === "triage" && !severity) return setFieldError("Choose a severity.");
    if (spec.id === "assign" && !workerId) return setFieldError("Choose a field worker.");
    if (spec.textRequired && !note) return setFieldError(`${spec.textLabel} is required.`);
    setFieldError(null);
    setBusy(true);
    setError(null);
    const v = incident.version;
    const outcome = await mutate(() => {
      if (spec.id === "triage") return api.triage(incident.id, v, severity as Severity, note);
      if (spec.id === "assign") return api.assign(incident.id, v, workerId, note);
      return api.transition(incident.id, v, spec.to!, note || undefined);
    }, reload);
    setBusy(false);
    if (outcome.kind === "ok") onApplied(outcome.incident, spec.label);
    else if (outcome.kind === "conflict") onConflict();
    else setError(outcome.error);
  }

  return (
    <Dialog open title={`${spec.label} ${incident.reference}`} onClose={onClose}>
      <form onSubmit={submit} noValidate className="space-y-4">
        {spec.id === "triage" && (
          <fieldset>
            <legend className="text-sm font-medium">Severity</legend>
            <div className="mt-2 space-y-2">
              {SEVERITIES.map((s) => (
                <label key={s} className="flex cursor-pointer items-start gap-2 rounded-md border border-slate-200 p-2 text-sm has-[:checked]:border-accent">
                  <input type="radio" name="severity" value={s} checked={severity === s} onChange={() => setSeverity(s)} className="mt-0.5" />
                  <span>
                    <span className="font-semibold">{s}</span> <span className="text-slate-600">{SEVERITY_HELP[s]}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
        )}
        {spec.id === "assign" && (
          <Field label="Field worker" htmlFor="worker">
            <select id="worker" value={workerId} onChange={(e) => setWorkerId(e.target.value)} className={inputClass}>
              <option value="">Choose...</option>
              {workers.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </Field>
        )}
        {spec.textLabel ? (
          <Field label={spec.textLabel} htmlFor="action-text">
            <textarea
              id="action-text"
              rows={3}
              maxLength={max}
              value={text}
              onChange={(e) => setText(e.target.value)}
              className={inputClass}
              required={spec.textRequired}
              aria-required={spec.textRequired}
            />
          </Field>
        ) : (
          <p className="text-sm text-slate-600">This moves the incident to in progress.</p>
        )}
        {fieldError && <p className="text-sm text-red-700" role="alert">{fieldError}</p>}
        {error !== null && <ErrorBox error={error} />}
        <div className="flex justify-end gap-2">
          <Button onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button type="submit" variant={spec.variant === "danger" ? "danger" : "primary"} disabled={busy}>
            {busy ? "Saving..." : spec.label}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
