"use client";
import { useEffect, useState } from "react";
import { env } from "@/lib/env";
import { supabase } from "@/lib/supabaseClient";
import { getUserContext } from "@/lib/auth";
import { apiPath } from "@/lib/api";

const API_BASE = env.apiBaseUrl; // NEXT_PUBLIC_API_BASE_URL, e.g. http://localhost:8002/api

/**
 * Live-data with safe mock fallback. Returns `fallback` immediately so the
 * dashboard always renders, then fetches `${API_BASE}${path}` with the user's
 * bearer token and swaps in real data when present + non-empty. `pick` extracts
 * the array/value from the JSON response.
 *
 *   const { data: people, live } = useLiveData("/workforce/people", MOCK_PEOPLE, j => j.people);
 */
export function useLiveData<T>(
  path: string,
  fallback: T,
  pick: (json: any) => T,
): { data: T; live: boolean; loading: boolean; refresh: () => void } {
  const [data, setData] = useState<T>(fallback);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(true);
  // Bumping this re-runs the effect. Pages had "Re-run scan" buttons that did
  // nothing because there was no way to ask for a refetch -- a control that
  // looks live and is decorative teaches a buyer to distrust the ones that
  // are not.
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        // Prefer a real Supabase session token; fall back to the app's dev token.
        let token = "";
        if (supabase) {
          const { data: { session } } = await supabase.auth.getSession();
          token = session?.access_token || "";
        }
        if (!token) {
          const ctx = await getUserContext();
          const orgId =
            ctx.orgId && ctx.orgId !== "local-dev-org"
              ? ctx.orgId
              : "11111111-1111-1111-1111-111111111111";
          const role = ctx.role ?? "owner";
          const email = ctx.email ?? "dev@local.test";
          const userId = "22222222-2222-2222-2222-222222222222";
          token = `dev:${orgId}:${role}:${email}:${userId}`;
        }
        // apiPath() strips a leading "/api" because API_BASE already ends in one.
        // apiFetch() was missing this and every caller writing "/api/equity/..."
        // got "/api/api/..." and a 404. Here the same slip would be WORSE than a
        // 404: the catch below keeps the mock fallback, so a wrong path renders
        // invented numbers with a "Sample data" pill nobody reads as a defect.
        const res = await fetch(`${API_BASE}${apiPath(path)}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          cache: "no-store",
        });
        if (!res.ok) return;
        const json = await res.json();
        const picked = pick(json);
        const nonEmpty = Array.isArray(picked) ? picked.length > 0 : picked != null;
        if (!cancelled && nonEmpty) {
          setData(picked);
          setLive(true);
        }
      } catch {
        /* keep the mock fallback — dashboard never breaks */
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [path, nonce]);

  return { data, live, loading, refresh: () => setNonce((n) => n + 1) };
}
