import Link from "next/link";
import { DEFAULT_TENANT } from "@/lib/config";

export default function Home() {
  return (
    <main className="mx-auto max-w-lg px-4 py-10">
      <p className="text-xs font-semibold uppercase tracking-wide text-accent">DrainWatch Ops</p>
      <h1 className="mt-1 text-2xl font-semibold">Waterlogging and blocked drains, from report to verified closure</h1>
      <div className="mt-6 grid gap-3">
        <Link href={`/report/?t=${DEFAULT_TENANT}`} className="rounded-md bg-accent px-4 py-3 text-center font-medium text-white hover:bg-accent-hover">
          Report a problem
        </Link>
        <Link href="/login/" className="rounded-md border border-slate-300 bg-white px-4 py-3 text-center font-medium hover:bg-slate-50">
          Staff sign in
        </Link>
      </div>
    </main>
  );
}
