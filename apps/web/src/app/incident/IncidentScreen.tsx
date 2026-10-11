"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { Button, ErrorBox, SeverityBadge, Spinner, StatusChip } from "@/components/ui";
import { api } from "@/lib/api";
import { availableActions, evidenceKinds, noActionReason, type ActionSpec } from "@/lib/actions";
import { isRetryable } from "@/lib/errors";
import { formatTime } from "@/lib/format";
import { CONFLICT_MESSAGE } from "@/lib/mutation";
import { useSession } from "@/lib/useSession";
import { useMembers } from "@/lib/useMembers";
import { keepEvidenceUrls, needsUrlRefresh, refreshDelayMs } from "@/lib/evidence";
import { TYPE_LABEL, type Incident, type IncidentEvent } from "@/lib/types";
import { ActionDialog } from "./ActionDialog";
import { EvidencePanel } from "./EvidencePanel";
import { Timeline } from "./Timeline";

export function IncidentScreen() {
  const { session } = useSession();
  const id = useSearchParams().get("id") ?? "";
  const { workers, error: workersError, nameOf, knownName } = useMembers(session);
  const [incident, setIncident] = useState<Incident | null>(null);
  const [events, setEvents] = useState<IncidentEvent[] | null>(null);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [eventsError, setEventsError] = useState<unknown>(null);
  const [active, setActive] = useState<ActionSpec | null>(null);
  const [notice, setNotice] = useState<{ tone: "ok" | "warn"; text: string } | null>(null);

  const reloadEvents = useCallback(async () => {
    setEventsError(null);
    try {
      setEvents((await api.events(id)).items);
    } catch (e) {
      setEventsError(e);
    }
  }, [id]);

  const refreshDetail = useCallback(async () => {
    setIncident(await api.get(id));
  }, [id]);

  const reload = useCallback(async () => {
    await Promise.all([refreshDetail(), reloadEvents()]);
  }, [refreshDetail, reloadEvents]);

  const initialLoad = useCallback(async () => {
    setLoadError(null);
    try {
      await reload();
    } catch (e) {
      setLoadError(e);
    }
  }, [reload]);

  useEffect(() => {
    if (session && id) void initialLoad();
  }, [session, id, initialLoad]);

  const delay = incident ? refreshDelayMs(incident) : null;
  useEffect(() => {
    if (delay === null) return;
    const timer = window.setTimeout(() => void refreshDetail().catch(() => undefined), delay);
    return () => window.clearTimeout(timer);
  }, [incident, delay, refreshDetail]);

  if (!session) return <Spinner label="Checking sign-in" />;

  function applied(next: Incident, message: string) {
    const merged = keepEvidenceUrls(next, incident);
    setIncident(merged);
    setNotice({ tone: "ok", text: message });
    void reloadEvents();
    if (needsUrlRefresh(merged)) void refreshDetail().catch(() => undefined);
  }

  function conflicted() {
    setActive(null);
    setNotice({ tone: "warn", text: CONFLICT_MESSAGE });
  }

  const actions = incident ? availableActions(incident, session) : [];
  const kinds = incident ? evidenceKinds(incident, session) : [];

  return (
    <>
      <AppHeader session={session} />
      <main className="mx-auto max-w-5xl px-4 py-5">
        <Link href="/queue/" className="text-sm text-accent hover:underline">
          Back to queue
        </Link>

        {!id ? (
          <ErrorBox message="No incident selected. Open one from the queue." />
        ) : loadError ? (
          <div className="mt-3">
            <ErrorBox error={loadError} onRetry={isRetryable(loadError) ? () => void initialLoad() : undefined} />
          </div>
        ) : !incident ? (
          <Spinner label="Loading incident" />
        ) : (
          <>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <h1 className="font-mono text-xl font-semibold">{incident.reference}</h1>
              <SeverityBadge severity={incident.severity} />
              <StatusChip status={incident.status} />
              <span className="text-xs text-slate-500">v{incident.version}</span>
            </div>

            {notice && (
              <div
                role={notice.tone === "warn" ? "alert" : "status"}
                className={`mt-3 flex items-start justify-between gap-3 rounded-md border p-3 text-sm ${
                  notice.tone === "warn" ? "border-amber-300 bg-amber-50 text-amber-900" : "border-emerald-200 bg-emerald-50 text-emerald-900"
                }`}
              >
                <span>{notice.text}</span>
                <button type="button" className="text-xs underline" onClick={() => setNotice(null)}>
                  Dismiss
                </button>
              </div>
            )}

            <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_20rem]">
              <div className="space-y-4">
                <section className="rounded-lg border border-slate-200 bg-white p-4">
                  <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
                    <Item label="Type">{TYPE_LABEL[incident.type]}</Item>
                    <Item label="Assignee">{nameOf(incident.assigned_to)}</Item>
                    <Item label="Reported">{formatTime(incident.created_at)}</Item>
                    <Item label="Last updated">{formatTime(incident.updated_at)}</Item>
                    <Item label="Location">
                      {incident.landmark || <span className="text-slate-400">No description</span>}
                      {incident.lat !== null && incident.lng !== null && (
                        <a
                          className="mt-0.5 block font-mono text-xs text-accent hover:underline"
                          href={`https://www.openstreetmap.org/?mlat=${incident.lat}&mlon=${incident.lng}#map=19/${incident.lat}/${incident.lng}`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          {incident.lat.toFixed(5)}, {incident.lng.toFixed(5)} (map)
                        </a>
                      )}
                    </Item>
                    <div className="sm:col-span-2">
                      <Item label="Description">
                        <p className="whitespace-pre-wrap">{incident.description}</p>
                      </Item>
                    </div>
                    {incident.resolution_summary && (
                      <div className="sm:col-span-2">
                        <Item label="Resolution summary">
                          <p className="whitespace-pre-wrap">{incident.resolution_summary}</p>
                        </Item>
                      </div>
                    )}
                  </dl>
                </section>

                <EvidencePanel
                  incident={incident}
                  kinds={kinds}
                  nameOf={nameOf}
                  onAdded={(next) => applied(next, "Photo added.")}
                  onConflict={() => void reload().catch(setLoadError)}
                  onUrlsExpired={refreshDetail}
                />

                <section className="rounded-lg border border-slate-200 bg-white p-4">
                  <div className="flex items-center justify-between">
                    <h2 className="text-sm font-semibold">Audit timeline</h2>
                    <Button className="min-h-8 text-xs" onClick={() => void reloadEvents()}>
                      Refresh
                    </Button>
                  </div>
                  {eventsError ? (
                    <div className="mt-3">
                      <ErrorBox error={eventsError} onRetry={() => void reloadEvents()} />
                    </div>
                  ) : events === null ? (
                    <Spinner label="Loading timeline" />
                  ) : (
                    <Timeline events={events} nameOf={nameOf} knownName={knownName} />
                  )}
                </section>
              </div>

              <aside className="order-first space-y-3 lg:order-none">
                <section className="rounded-lg border border-slate-200 bg-white p-4 lg:sticky lg:top-4">
                  <h2 className="text-sm font-semibold">Actions</h2>
                  {actions.length === 0 ? (
                    <p className="mt-2 text-sm text-slate-600">{noActionReason(incident, session, nameOf(incident.assigned_to))}</p>
                  ) : (
                    <div className="mt-3 grid gap-2">
                      {actions.map((a) => {
                        const noWorkers = a.id === "assign" && workers.length === 0;
                        return (
                          <div key={a.id}>
                            <Button variant={a.variant} className="w-full" disabled={noWorkers} onClick={() => setActive(a)}>
                              {a.label}
                            </Button>
                            {noWorkers && (
                              <p className="mt-1 text-xs text-slate-500">
                                {workersError ? "Could not load field workers." : "No field workers available to assign."}
                              </p>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </section>
              </aside>
            </div>

            <ActionDialog
              action={active}
              incident={incident}
              workers={workers}
              onClose={() => setActive(null)}
              onApplied={(next, label) => {
                setActive(null);
                applied(next, `${label}: done.`);
              }}
              onConflict={conflicted}
              reload={reload}
            />
          </>
        )}
      </main>
    </>
  );
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-slate-900">{children}</dd>
    </div>
  );
}
