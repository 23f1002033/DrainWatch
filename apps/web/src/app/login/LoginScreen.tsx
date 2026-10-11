"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Button, ErrorBox, Field, inputClass } from "@/components/ui";
import { signIn } from "@/lib/auth";
import { config } from "@/lib/config";
import { getSession } from "@/lib/session";

function safeNext(raw: string | null): string {
  return raw && raw.startsWith("/") && !raw.startsWith("//") ? raw : "/queue/";
}

export function LoginScreen() {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const configured = Boolean(config.userPoolId && config.clientId);

  useEffect(() => {
    if (getSession()) router.replace(next);
  }, [next, router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim() || !password) {
      setError("Enter your email and password.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await signIn(email, password);
      router.replace(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-sm px-4 py-10">
      <p className="text-xs font-semibold uppercase tracking-wide text-accent">DrainWatch Ops</p>
      <h1 className="mt-1 text-xl font-semibold">Staff sign in</h1>
      <form onSubmit={submit} noValidate className="mt-5 space-y-4 rounded-lg border border-slate-200 bg-white p-5">
        <Field label="Email" htmlFor="email">
          <input id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} className={inputClass} />
        </Field>
        <Field label="Password" htmlFor="password">
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputClass}
          />
        </Field>
        {error && <ErrorBox message={error} />}
        {!configured && <ErrorBox message="Sign-in is not configured for this build (missing user pool settings)." />}
        <Button type="submit" variant="primary" className="w-full" disabled={busy || !configured}>
          {busy ? "Signing in..." : "Sign in"}
        </Button>
      </form>
    </main>
  );
}
