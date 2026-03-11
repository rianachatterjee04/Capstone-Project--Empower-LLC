import { env } from "./env";
import { getUserContext } from "./auth";

async function getToken(): Promise<string | null> {
  const ctx = await getUserContext();

  const orgId =
    ctx.orgId && ctx.orgId !== "local-dev-org"
      ? ctx.orgId
      : "11111111-1111-1111-1111-111111111111";

  const role = ctx.role ?? "owner";
  const email = ctx.email ?? "dev@local.test";
  const userId = "22222222-2222-2222-2222-222222222222";

  return `dev:${orgId}:${role}:${email}:${userId}`;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getToken();

  const headers = new Headers(init?.headers ?? {});
  headers.set("Content-Type", "application/json");

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${env.apiBaseUrl}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });

  if (!res.ok) {
    let err: any = null;
    let text = "";

    try {
      err = await res.json();
    } catch {
      try {
        text = await res.text();
      } catch {}
    }

    console.error("API error response:", {
      status: res.status,
      path,
      err,
      text,
    });

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
  return apiFetch<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function apiPatch<T>(path: string, body: any): Promise<T> {
  return apiFetch<T>(path, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}
