import { INCIDENT_TYPES, type IncidentType, type PublicReport } from "./types";

export interface ReportForm {
  type: IncidentType | "";
  description: string;
  landmark: string;
  coords: { lat: number; lng: number } | null;
}

export type ReportErrors = Partial<Record<"type" | "description" | "landmark" | "coords", string>>;

export const DESCRIPTION_MIN = 3;
export const DESCRIPTION_MAX = 1000;
export const LANDMARK_MAX = 200;

export function validateReport(form: ReportForm): { errors: ReportErrors; body: PublicReport | null } {
  const errors: ReportErrors = {};
  const description = form.description.trim();
  const landmark = form.landmark.trim();
  if (!form.type || !INCIDENT_TYPES.includes(form.type)) errors.type = "Choose what you are reporting.";
  if (description.length < DESCRIPTION_MIN) errors.description = `Describe the problem in at least ${DESCRIPTION_MIN} characters.`;
  else if (description.length > DESCRIPTION_MAX) errors.description = `Keep the description under ${DESCRIPTION_MAX} characters.`;
  if (landmark.length > LANDMARK_MAX) errors.landmark = `Keep the location under ${LANDMARK_MAX} characters.`;
  if (!landmark && !form.coords) errors.landmark = "Describe where it is, or use your location.";
  if (form.coords) {
    const { lat, lng } = form.coords;
    if (!(lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180)) errors.coords = "Location is out of range.";
  }
  if (Object.keys(errors).length > 0 || !form.type) return { errors, body: null };
  const body: PublicReport = { type: form.type, description };
  if (landmark) body.landmark = landmark;
  if (form.coords) {
    body.lat = Number(form.coords.lat.toFixed(6));
    body.lng = Number(form.coords.lng.toFixed(6));
  }
  return { errors, body };
}

export const TENANT_PATTERN = /^[a-z0-9-]{1,64}$/;
