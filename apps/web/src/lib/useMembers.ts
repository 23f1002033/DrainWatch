"use client";

import { useEffect, useState } from "react";
import { api } from "./api";
import type { Session } from "./session";
import type { Member } from "./types";

const ROLE_LABEL = { operator: "Operator", field_worker: "Field worker" } as const;

export function useMembers(session: Session | null): {
  workers: Member[];
  error: unknown;
  nameOf: (sub: string | null) => string;
  knownName: (sub: string) => string | null;
} {
  const [members, setMembers] = useState<Member[]>([]);
  const [error, setError] = useState<unknown>(null);
  const signedIn = Boolean(session);

  useEffect(() => {
    if (!signedIn) return;
    let alive = true;
    api
      .members()
      .then((r) => alive && setMembers(r.items))
      .catch((e) => alive && setError(e));
    return () => {
      alive = false;
    };
  }, [signedIn]);

  function knownName(sub: string): string | null {
    if (sub === "anonymous") return "Public reporter";
    if (session && sub === session.sub) return "You";
    return members.find((m) => m.id === sub)?.name ?? null;
  }

  function nameOf(sub: string | null): string {
    if (!sub) return "Unassigned";
    const known = knownName(sub);
    if (known) return known;
    const role = members.find((m) => m.id === sub)?.role;
    return role ? ROLE_LABEL[role] : `User ${sub.slice(0, 8)}`;
  }

  return { workers: members.filter((m) => m.role === "field_worker"), error, nameOf, knownName };
}
