"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/Button";
import { signInDemo, isSignedIn } from "@/lib/session";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Already signed in? Go straight to the workspace.
  useEffect(() => {
    if (isSignedIn()) router.replace("/app");
  }, [router]);

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    if (signInDemo(email, password)) {
      // router.replace prepends the /people basePath.
      router.replace("/app");
    } else {
      setSubmitting(false);
      setError("That email or password is not correct. Please try again.");
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-canvas px-6 py-12">
      <div className="w-full max-w-sm">
        <div className="text-2xl font-semibold tracking-tight text-ink" style={{ fontFamily: "Arial, sans-serif" }}>
          Fintra
        </div>
        <div className="mt-1 text-sm text-ink/50">People workspace</div>

        <form
          onSubmit={onSubmit}
          className="mt-8 rounded-2xl border border-black/10 bg-white p-6 shadow-sm"
        >
          <h1 className="text-lg font-semibold text-ink">Sign in</h1>
          <p className="mt-1 text-sm text-ink/55">Welcome back. Enter your details to continue.</p>

          <label className="mt-6 block text-sm font-medium text-ink/80">
            Email
            <input
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="mt-1.5 w-full rounded-xl border border-black/15 px-3 py-2 text-sm outline-none focus:border-black/40"
              placeholder="you@company.com"
            />
          </label>

          <label className="mt-4 block text-sm font-medium text-ink/80">
            Password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="mt-1.5 w-full rounded-xl border border-black/15 px-3 py-2 text-sm outline-none focus:border-black/40"
              placeholder="Your password"
            />
          </label>

          {error && (
            <div className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
          )}

          <Button type="submit" disabled={submitting} className="mt-6 w-full">
            {submitting ? "Signing in..." : "Sign in"}
          </Button>
        </form>

        <div className="mt-6 text-xs text-ink/45">
          Part of the Fintra platform. Finance, Trust, and People share one login.
        </div>
      </div>
    </div>
  );
}
