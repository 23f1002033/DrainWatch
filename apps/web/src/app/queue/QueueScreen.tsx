"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { Button, Empty, ErrorBox, SeverityBadge, Spinner, StatusChip } from "@/components/ui";
import { api } from "@/lib/api";
import { age } from "@/lib/format";
import { useSession } from "@/lib/useSession";
import { useMembers } from "@/lib/useMembers";
import { OVERDUE_RULES, QUICK_VIEWS, applyQuickView, isOverdue, quickViewCounts, type QuickViewId } from "@/lib/queue";
import dynamic from "next/dynamic";
import {
  INCIDENT_TYPES,
  SEVERITIES,
  STATUSES,
  STATUS_LABEL,
  TYPE_LABEL,
  type Incident,
  type IncidentType,
  type QueueQuery,
  type Severity,
  type Status,
} from "@/lib/types";

const QueueMap = dynamic(() => import("./QueueMap").then((m) => m.QueueMap), {
  ssr: false,
  loading: () => <Spinner label="Loading map" />,
});

const AGE_OPTIONS = [
  { value: "", label: "Any age" },
  { value: "1", label: "Older than 1 hour" },
  { value: "4", label: "Older than 4 hours" },
  { value: "24", label: "Older than 24 hours" },
  { value: "72", label: "Older than 3 days" },
];

function pick<T extends string>(value: string | null, allowed: readonly T[]): T | undefined {
  return value && (allowed as readonly string[]).includes(value) ? (value as T) : undefined;
}

export function QueueScreen() {
  const { session } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const { nameOf } = useMembers(session);

  const isWorker = session?.role === "field_worker";
  const tab = isWorker && params.get("tab") !== "all" ? "mine" : "all";
  const view = params.get("view") === "map" ? "map" : "list";
  const quick: QuickViewId = QUICK_VIEWS.find((v) => v.id === params.get("qv"))?.id ?? "open";
  const query: QueueQuery = useMemo(() => {
    const hours = Number(params.get("age"));
    return {
      status: pick<Status>(params.get("status"), STATUSES),
      severity: pick<Severity>(params.get("severity"), SEVERITIES),
      type: pick<IncidentType>(params.get("type"), INCIDENT_TYPES),
      older_than_hours: AGE_OPTIONS.some((o) => o.value && Number(o.value) === hours) ? hours : undefined,
    };
  }, [params]);
  const pageSize = useMemo(() => {
    const n = Number(params.get("limit"));
    return Number.isInteger(n) && n >= 1 && n <= 100 ? n : 25;
  }, [params]);

  const [items, setItems] = useState<Incident[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [moreError, setMoreError] = useState<unknown>(null);

  const seq = useRef(0);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const load = useCallback(async () => {
    const mine = ++seq.current;
    setLoading(true);
    setError(null);
    setMoreError(null);
    try {
      const page = await api.queue({ ...query, limit: pageSize });
      if (mine !== seq.current) return;
      setNow(Date.now());
      setItems(page.items);
      setCursor(page.next_cursor);
    } catch (e) {
      if (mine === seq.current) setError(e);
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, [query, pageSize]);

  useEffect(() => {
    if (session) void load();
  }, [session, load]);

  async function loadMore() {
    if (!cursor) return;
    const mine = seq.current;
    setLoadingMore(true);
    setMoreError(null);
    try {
      const page = await api.queue({ ...query, cursor, limit: pageSize });
      if (mine !== seq.current) return;
      setItems((prev) => [...prev, ...page.items.filter((i) => !prev.some((p) => p.id === i.id))]);
      setCursor(page.next_cursor);
    } catch (e) {
      setMoreError(e);
    } finally {
      setLoadingMore(false);
    }
  }

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    const qs = next.toString();
    router.replace(`/queue/${qs ? `?${qs}` : ""}`, { scroll: false });
  }

  if (!session) return <Spinner label="Checking sign-in" />;

  const scoped = tab === "mine" ? items.filter((i) => i.assigned_to === session.sub) : items;
  const counts = quickViewCounts(scoped, now);
  const visible = applyQuickView(scoped, quick, now);
  const quickLabel = QUICK_VIEWS.find((v) => v.id === quick)!.label;
  const filtersActive = Boolean(query.status || query.severity || query.type || query.older_than_hours);

  return (
    <>
      <AppHeader session={session} />
      <main className="mx-auto max-w-6xl px-4 py-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-lg font-semibold">{tab === "mine" ? "My work" : "Incident queue"}</h1>
          <div className="flex gap-2">
            <div role="group" aria-label="View" className="inline-flex rounded-md border border-slate-300 bg-white p-0.5">
              {(["list", "map"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={view === v}
                  onClick={() => setParam("view", v === "map" ? "map" : "")}
                  className={`rounded px-3 py-1.5 text-sm ${view === v ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"}`}
                >
                  {v === "list" ? "List" : "Map"}
                </button>
              ))}
            </div>
            {session.role === "operator" && (
              <Link href={`/poster/?t=${session.tenantId}`} className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm hover:bg-slate-50">
                QR poster
              </Link>
            )}
            <Button onClick={() => void load()} disabled={loading}>
              Refresh
            </Button>
          </div>
        </div>

        {isWorker && (
          <div role="tablist" aria-label="Queue view" className="mt-3 inline-flex rounded-md border border-slate-300 bg-white p-0.5">
            {(["mine", "all"] as const).map((t) => (
              <button
                key={t}
                role="tab"
                type="button"
                aria-selected={tab === t}
                onClick={() => setParam("tab", t === "all" ? "all" : "")}
                className={`rounded px-3 py-1.5 text-sm ${tab === t ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"}`}
              >
                {t === "mine" ? "My work" : "All incidents"}
              </button>
            ))}
          </div>
        )}

        <div className="mt-3 overflow-x-auto">
          <div role="tablist" aria-label="Quick views" className="flex min-w-max gap-1 border-b border-slate-200">
            {QUICK_VIEWS.map((v) => {
              const selected = quick === v.id;
              return (
                <button
                  key={v.id}
                  role="tab"
                  type="button"
                  aria-selected={selected}
                  onClick={() => setParam("qv", v.id === "open" ? "" : v.id)}
                  className={`-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm whitespace-nowrap ${
                    selected ? "border-accent font-medium text-slate-900" : "border-transparent text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {v.label}
                  <span
                    className={`rounded-full px-1.5 text-xs tabular-nums ${
                      v.id === "overdue" && counts.overdue > 0 ? "bg-red-100 text-red-800" : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {loading ? "-" : counts[v.id]}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
        <p className="mt-1.5 text-xs text-slate-500">
          <span className="font-medium text-red-700">Overdue</span>: not triaged within {OVERDUE_RULES.triageWithinHours} h, or not resolved
          within {OVERDUE_RULES.resolveWithinHours.S1} h (S1), {OVERDUE_RULES.resolveWithinHours.S2} h (S2), {OVERDUE_RULES.resolveWithinHours.S3} h
          (S3), counted from report time. Counts cover the {scoped.length} loaded incidents.
        </p>

        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
          <Select label="Status" value={query.status ?? ""} onChange={(v) => setParam("status", v)}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABEL[s]}
              </option>
            ))}
          </Select>
          <Select label="Severity" value={query.severity ?? ""} onChange={(v) => setParam("severity", v)}>
            <option value="">All severities</option>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
          <Select label="Type" value={query.type ?? ""} onChange={(v) => setParam("type", v)}>
            <option value="">All types</option>
            {INCIDENT_TYPES.map((t) => (
              <option key={t} value={t}>
                {TYPE_LABEL[t]}
              </option>
            ))}
          </Select>
          <Select label="Age" value={query.older_than_hours?.toString() ?? ""} onChange={(v) => setParam("age", v)}>
            {AGE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
          <div className="flex items-end">
            <Button
              className="w-full"
              disabled={!filtersActive}
              title={filtersActive ? undefined : "No filters applied"}
              onClick={() => {
                const keep = new URLSearchParams();
                for (const k of ["tab", "view", "limit", "qv"]) {
                  const v = params.get(k);
                  if (v) keep.set(k, v);
                }
                const qs = keep.toString();
                router.replace(`/queue/${qs ? `?${qs}` : ""}`, { scroll: false });
              }}
            >
              Clear filters
            </Button>
          </div>
        </div>

        <section className="mt-4" aria-live="polite" aria-busy={loading}>
          {loading ? (
            <Spinner label="Loading incidents" />
          ) : error ? (
            <ErrorBox error={error} onRetry={() => void load()} />
          ) : visible.length === 0 ? (
            <Empty>
              {scoped.length > 0
                ? `Nothing in ${quickLabel} among the ${scoped.length} loaded incidents.${cursor ? " Load more to check older ones." : ""}`
                : tab === "mine"
                  ? cursor
                    ? "Nothing assigned to you on this page. Load more to check older incidents."
                    : "Nothing is assigned to you right now."
                  : filtersActive
                    ? "No incidents match these filters."
                    : "No incidents reported yet."}
            </Empty>
          ) : view === "map" ? (
            <QueueMap items={visible} />
          ) : (
            <IncidentList items={visible} nameOf={nameOf} now={now} />
          )}

          {!loading && !error && (
            <div className="mt-3 flex flex-col items-center gap-2">
              {moreError !== null && <ErrorBox error={moreError} onRetry={() => void loadMore()} />}
              {cursor ? (
                <Button onClick={() => void loadMore()} disabled={loadingMore}>
                  {loadingMore ? "Loading..." : "Load more"}
                </Button>
              ) : (
                items.length > 0 && <p className="text-xs text-slate-500">End of list ({items.length} loaded)</p>
              )}
            </div>
          )}
        </section>
      </main>
    </>
  );
}

function Select({ label, value, onChange, children }: { label: string; value: string; onChange: (v: string) => void; children: React.ReactNode }) {
  const id = `f-${label.toLowerCase()}`;
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-slate-600">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-0.5 block min-h-10 w-full rounded-md border border-slate-300 bg-white px-2 text-sm"
      >
        {children}
      </select>
    </div>
  );
}

function OverdueChip() {
  return <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs font-medium text-red-800 ring-1 ring-red-200 ring-inset">Overdue</span>;
}

function Location({ incident }: { incident: Incident }) {
  return (
    <>
      <span className="block truncate text-slate-800">
        {incident.landmark || (incident.lat !== null ? "Location shared (GPS)" : <span className="text-slate-400">No location text</span>)}
      </span>
      <span className="block truncate text-xs text-slate-500">{incident.description}</span>
    </>
  );
}

function IncidentList({ items, nameOf, now }: { items: Incident[]; nameOf: (sub: string | null) => string; now: number }) {
  const router = useRouter();
  const open = (id: string) => router.push(`/incident/?id=${id}`);
  return (
    <>
      <ul className="space-y-2 md:hidden">
        {items.map((i) => (
          <li key={i.id}>
            <Link href={`/incident/?id=${i.id}`} className="block rounded-lg border border-slate-200 bg-white p-3 hover:border-slate-400">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs text-slate-500">{i.reference}</span>
                <span className="flex items-center gap-1.5 text-xs text-slate-500">
                  {isOverdue(i, now) && <OverdueChip />}
                  {age(i.created_at, now)} ago
                </span>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <SeverityBadge severity={i.severity} />
                <StatusChip status={i.status} />
                <span className="text-sm font-medium">{TYPE_LABEL[i.type]}</span>
              </div>
              <div className="mt-1 text-sm">
                <Location incident={i} />
              </div>
              <p className="mt-1 text-xs text-slate-500">{nameOf(i.assigned_to)}</p>
            </Link>
          </li>
        ))}
      </ul>
      <div className="hidden overflow-hidden rounded-lg border border-slate-200 bg-white md:block">
        <table className="w-full table-fixed text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="w-32 px-3 py-2 font-medium">Reference</th>
              <th className="w-24 px-3 py-2 font-medium">Severity</th>
              <th className="w-28 px-3 py-2 font-medium">Status</th>
              <th className="w-32 px-3 py-2 font-medium">Type</th>
              <th className="px-3 py-2 font-medium">Location</th>
              <th className="w-32 px-3 py-2 font-medium">Assignee</th>
              <th className="w-32 px-3 py-2 font-medium">Age</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((i) => (
              <tr
                key={i.id}
                tabIndex={0}
                role="link"
                aria-label={`Open incident ${i.reference}`}
                onClick={() => open(i.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    open(i.id);
                  }
                }}
                className="cursor-pointer hover:bg-slate-50 focus-visible:bg-blue-50 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent"
              >
                <td className="px-3 py-2 font-mono text-accent">{i.reference}</td>
                <td className="px-3 py-2">
                  <SeverityBadge severity={i.severity} />
                </td>
                <td className="px-3 py-2">
                  <StatusChip status={i.status} />
                </td>
                <td className="px-3 py-2">{TYPE_LABEL[i.type]}</td>
                <td className="px-3 py-2" title={`${i.landmark ?? ""}\n${i.description}`.trim()}>
                  <Location incident={i} />
                </td>
                <td className="truncate px-3 py-2 text-slate-700">{nameOf(i.assigned_to)}</td>
                <td className="px-3 py-2 text-slate-500" title={i.created_at}>
                  <span className="flex items-center gap-1.5">
                    {age(i.created_at, now)}
                    {isOverdue(i, now) && <OverdueChip />}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
