import { env } from "./env";
import { supabase } from "./supabaseClient";

const DEV_TOKEN = "dev:11111111-1111-1111-1111-111111111111:employee:dev@local.test:22222222-2222-2222-2222-222222222222";

async function getToken(): Promise<string> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? DEV_TOKEN;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getToken();
  const res = await fetch(`${env.apiBaseUrl}${path}`, {
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