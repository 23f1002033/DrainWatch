import type { Incident } from "./types";

// Mutation responses carry no evidence URLs; keep the ones we already have until the detail refetch lands.
export function keepEvidenceUrls(next: Incident, prev: Incident | null): Incident {
  if (!prev) return next;
  const urls = new Map(prev.evidence.filter((e) => e.url).map((e) => [e.key, e]));
  return {
    ...next,
    evidence: next.evidence.map((e) => {
      const known = urls.get(e.key);
      return e.url || !known ? e : { ...e, url: known.url, url_expires_in: known.url_expires_in };
    }),
  };
}

export function needsUrlRefresh(incident: Incident): boolean {
  return incident.evidence.some((e) => !e.url);
}

// Refetch a little before presigned URLs expire so thumbnails and full-size links keep working.
export function refreshDelayMs(incident: Incident, marginSeconds = 30): number | null {
  const ttls = incident.evidence.map((e) => e.url_expires_in).filter((t): t is number => typeof t === "number");
  if (ttls.length === 0) return null;
  return Math.max(10, Math.min(...ttls) - marginSeconds) * 1000;
}
