"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { signOut } from "@/lib/auth";
import { tenantName } from "@/lib/config";
import type { Session } from "@/lib/session";

const ROLE_LABEL = { operator: "Operator", field_worker: "Field worker" } as const;

export function AppHeader({ session }: { session: Session }) {
  const router = useRouter();
  return (
    <header className="no-print border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-2 text-sm">
          <Link href="/queue/" className="font-semibold whitespace-nowrap">
            DrainWatch Ops
          </Link>
          <span className="truncate border-l border-slate-300 pl-2 text-slate-600">{tenantName(session.tenantId)}</span>
        </div>
        <div className="flex shrink-0 items-center gap-3 text-sm">
          <span className="hidden text-slate-600 sm:inline">{session.email}</span>
          <span className="hidden rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-700 sm:inline">{ROLE_LABEL[session.role]}</span>
          <button
            type="button"
            className="rounded px-2 py-1 whitespace-nowrap text-slate-700 hover:bg-slate-100"
            onClick={() => {
              signOut();
              router.replace("/login/");
            }}
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}
