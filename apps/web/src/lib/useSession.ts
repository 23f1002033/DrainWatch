"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getSession, onSessionChange, type Session } from "./session";

export function useSession(required = true): { session: Session | null; ready: boolean } {
  const router = useRouter();
  const [session, setState] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const sync = () => {
      const s = getSession();
      setState(s);
      setReady(true);
      if (!s && required) {
        const next = window.location.pathname + window.location.search;
        router.replace(`/login/?next=${encodeURIComponent(next)}`);
      }
    };
    sync();
    const timer = window.setInterval(sync, 30000);
    const off = onSessionChange(sync);
    return () => {
      off();
      window.clearInterval(timer);
    };
  }, [required, router]);

  return { session, ready };
}
