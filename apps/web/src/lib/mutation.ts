import { isConflict } from "./errors";
import type { Incident } from "./types";

export type MutationOutcome =
  | { kind: "ok"; incident: Incident }
  | { kind: "conflict"; reloadError: unknown }
  | { kind: "error"; error: unknown };

export async function mutate(action: () => Promise<Incident>, reload: () => Promise<void>): Promise<MutationOutcome> {
  try {
    return { kind: "ok", incident: await action() };
  } catch (error) {
    if (!isConflict(error)) return { kind: "error", error };
    try {
      await reload();
      return { kind: "conflict", reloadError: null };
    } catch (reloadError) {
      return { kind: "conflict", reloadError };
    }
  }
}

export const CONFLICT_MESSAGE = "This incident was updated by someone else. The latest version is shown below; review it and try again.";
