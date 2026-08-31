import { env } from "./env";
import { supabase } from "./supabaseClient";

// The signed-out dev identity for this portal.
//
// The email matters: server-side "me" lookups resolve the caller to an employee
// row by user_id OR email, and `dev@local.test` matches nobody in the seeded
// org. So every self-service surface answered "no record is linked to your
// account" -- correct, and useless as a demo. Pointing the dev identity at a
// real seeded employee makes the portal show a real person's real data.
const DEV_EMPLOYEE_EMAIL = process.env.NEXT_PUBLIC_DEV_EMPLOYEE_EMAIL || "liam.eng@northwind.test";
const DEV_TOKEN = `dev:11111111-1111-1111-1111-111111111111:employee:${DEV_EMPLOYEE_EMAIL}:22222222-2222-2222-2222-222222222222`;

async function getToken(): Promise<string> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? DEV_TOKEN;
}

/**
 * Strip one leading "/api" because env.apiBaseUrl already ends in one.
 *
 * WHY THIS EXISTS
 * apiBaseUrl is "http://localhost:8000/api" (and ".../api" in production), and
 * this module joined it to the caller's path unchanged. Four callers write
 * "/api/comp/..." -- the whole compensation surface of this app --
 * so every one of them requested /api/api/equity/... and got a 404.
 *
 *   GET /api/api/comp/total          404
 *   GET /api/comp/total              200
 *
 * An employee opening their own equity or total-comp page saw an error. The
 * employer app had exactly this defect and exactly this fix; this package has
 * no tests, so nothing carried it across.
 */
export function apiPath(path: string): string {
  return path.startsWith("/api/") ? path.slice(4) : path;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getToken();
  const res = await fetch(`${env.apiBaseUrl}${apiPath(path)}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    let err: any = {};
    let text = "";
    try {
      err = await res.json();
    } catch {
      try { text = await res.text(); } catch {}
    }
    throw new Error(
      err?.detail
        ? typeof err.detail === "string"
          ? err.detail
          : JSON.stringify(err.detail)
        : err?.message || text || `HTTP ${res.status}`
    );
  }

  const contentType = res.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    return undefined as T;
  }

  return (await res.json()) as T;
}

export async function apiPost<T>(path: string, body: any): Promise<T> {
  return apiFetch<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export async function apiPatch<T>(path: string, body: any): Promise<T> {
  return apiFetch<T>(path, { method: "PATCH", body: JSON.stringify(body) });
}