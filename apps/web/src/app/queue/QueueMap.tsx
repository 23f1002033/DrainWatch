"use client";

import "leaflet/dist/leaflet.css";
import type { Map as LeafletMap } from "leaflet";
import { useEffect, useRef, useState } from "react";
import { Empty, ErrorBox } from "@/components/ui";
import { STATUS_LABEL, TYPE_LABEL, type Incident, type Severity } from "@/lib/types";

const COLOR: Record<Severity | "none", string> = { S1: "#dc2626", S2: "#d97706", S3: "#64748b", none: "#1d4ed8" };

function escape(s: string): string {
  return s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

export function QueueMap({ items }: { items: Incident[] }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<LeafletMap | null>(null);
  const [failed, setFailed] = useState(false);
  const located = items.filter((i) => i.lat !== null && i.lng !== null);
  const markersKey = located.map((i) => `${i.id}:${i.version}`).join(",");

  useEffect(() => {
    if (!el.current || located.length === 0) return;
    let cancelled = false;
    import("leaflet")
      .then((L) => {
        if (cancelled || !el.current) return;
        map.current?.remove();
        const m = L.map(el.current, { scrollWheelZoom: false });
        map.current = m;
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        }).addTo(m);
        const bounds = L.latLngBounds([]);
        for (const i of located) {
          const ll = L.latLng(i.lat!, i.lng!);
          bounds.extend(ll);
          L.circleMarker(ll, { radius: 9, color: "#fff", weight: 2, fillColor: COLOR[i.severity ?? "none"], fillOpacity: 0.95 })
            .addTo(m)
            .bindPopup(
              `<strong>${escape(i.reference)}</strong> ${i.severity ?? "Untriaged"} - ${STATUS_LABEL[i.status]}<br>${escape(TYPE_LABEL[i.type])}: ${escape(
                i.landmark ?? i.description,
              )}<br><a href="/incident/?id=${encodeURIComponent(i.id)}">Open incident</a>`,
            );
        }
        m.fitBounds(bounds, { padding: [30, 30], maxZoom: 18 });
      })
      .catch(() => setFailed(true));
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
    };
  }, [markersKey]);

  if (located.length === 0) return <Empty>None of the loaded incidents have a shared location. Reports without GPS only appear in the list.</Empty>;
  return (
    <div>
      {failed && <ErrorBox message="The map could not be loaded." />}
      <div ref={el} className="h-[60vh] min-h-80 w-full rounded-lg border border-slate-200" aria-label="Map of incidents with a location" role="region" />
      <p className="mt-2 flex flex-wrap gap-3 text-xs text-slate-600">
        <span>
          {located.length} of {items.length} loaded incidents have a location.
        </span>
        {(["S1", "S2", "S3", "none"] as const).map((s) => (
          <span key={s} className="inline-flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: COLOR[s] }} aria-hidden />
            {s === "none" ? "Untriaged" : s}
          </span>
        ))}
      </p>
    </div>
  );
}
