"use client";

import { useEffect, useState } from "react";
import { api } from "./api";
import type { Session } from "./session";
import type { Worker } from "./types";

export function useWorkers(session: Session | null): {
  workers: Worker[];
  error: unknown;
  nameOf: (sub: string | null) => string;
  knownName: (sub: string) => string | null;
} {
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [error, setError] = useState<unknown>(null);
  const isOperator = session?.role === "operator";

  useEffect(() => {
    if (!isOperator) return;
    let alive = true;
    api
      .workers()
      .then((r) => alive && setWorkers(r.items))
      .catch((e) => alive && setError(e));
    return () => {
      alive = false;
    };
  }, [isOperator]);

  function knownName(sub: string): string | null {
    if (sub === "anonymous") return "Public reporter";
    if (session && sub === session.sub) return "You";
    return workers.find((w) => w.id === sub)?.name ?? null;
  }

  function nameOf(sub: string | null): string {
    if (!sub) return "Unassigned";
    return knownName(sub) ?? `User ${sub.slice(0, 8)}`;
  }

  return { workers, error, nameOf, knownName };
}
