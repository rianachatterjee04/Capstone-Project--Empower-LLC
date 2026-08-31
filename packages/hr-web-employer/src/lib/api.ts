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

/**
 * Normalise a path against the API base.
 *
 * The server hands out absolute API paths -- `/api/interview-v2/{id}/media/1`
 * -- and `env.apiBaseUrl` already ends in `/api`. Concatenating them produced
 * `/api/api/...` and a 404, which surfaced as `video.duration === NaN` and a
 * seek that silently did nothing. Both forms are accepted here so a
 * server-supplied href and a hand-written path behave the same.
 */
/**
 * The Authorization header the rest of the app sends.
 *
 * WHY THIS IS EXPORTED
 * `interviewCapture.uploadPart` takes a `headers` option and the candidate
 * page passed none, so every recorded part was POSTed with no credentials and
 * refused by `require_org`. The page showed "the recording could not be
 * uploaded: HTTP 401" and nobody saw it, because exercising that path needs a
 * camera. That is the reason the recording pipeline read as NOT_CONNECTED end
 * to end: not a missing feature, a missing header.
 */
export async function authHeaders(): Promise<Record<string, string>> {
  const token = await getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function apiPath(path: string): string {
  return path.startsWith("/api/") ? path.slice(4) : path;
}

/**
 * The human sentence out of a FastAPI error body.
 *
 * WHY THIS IS NOT JSON.stringify
 * The refusals worth showing a user are the structured ones. Issuing a grant
 * larger than the option pool raised
 *
 *   {"refused": true, "reason": "POOL_EXHAUSTED",
 *    "message": "3,000,000 shares requested but only 2,000,000 remain ...",
 *    "pool_authorized": 2000000, "granted_outstanding": 0, "pools": [...]}
 *
 * and the equity page printed that, braces and UUIDs and all, where the
 * explanation should have been. The product had done exactly the right thing
 * and the screen made it look broken.
 *
 * So: a string detail is the message; an object detail with a `message` (or
 * `reason`, or `detail`) is that field; a validation array is its messages
 * joined. Anything genuinely unrecognised still falls back to JSON rather than
 * silently dropping what the server said.
 */
export function detailMessage(err: any): string {
  const d = err?.detail ?? err;
  if (d == null) return "";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    // FastAPI 422: [{loc, msg, type}, ...]
    const msgs = d.map((e) => e?.msg ?? e?.message).filter(Boolean);
    return msgs.length ? msgs.join("; ") : JSON.stringify(d);
  }
  if (typeof d === "object") {
    const m = d.message ?? d.reason ?? d.detail ?? d.error;
    if (typeof m === "string" && m.trim()) return m;
    return JSON.stringify(d);
  }
  return String(d);
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getToken();

  const headers = new Headers(init?.headers ?? {});
  headers.set("Content-Type", "application/json");

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  // apiPath() strips a leading "/api" because env.apiBaseUrl already ends in
  // one. Line 135 used it and this one did not, so every caller writing
  // "/api/equity/..." -- which is what the equity page does throughout --
  // produced "/api/api/equity/..." and a 404. The whole equity surface rendered
  // the word "Not Found" under a header promising a cap table, 409A and ASC 718
  // expense posting straight to the ledger.
  const res = await fetch(`${env.apiBaseUrl}${apiPath(path)}`, {
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

    // The status rides along on the error. Without it a caller can only match
    // on message text, and the retry policy in Providers.tsx cannot tell a 404
    // -- an answer -- from a 503 -- an outage worth retrying.
    const failure = new Error(detailMessage(err) || text || `HTTP ${res.status}`) as Error & {
      status?: number;
      body?: unknown;
    };
    failure.status = res.status;
    failure.body = err;
    throw failure;
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


/**
 * Fetch a protected binary and hand back a blob: URL.
 *
 * WHY THE PLAYER CANNOT JUST USE THE API URL
 * A <video src="..."> request is made by the browser's media loader, which
 * sends no Authorization header. Pointing the element straight at
 * `/interview-v2/{id}/media/1` produced a 401, and the symptom was silent:
 * `video.duration` came back NaN and the recruiter's click-to-seek did
 * nothing, with no error anywhere on the page.
 *
 * Fetching with the header and handing the element a blob is the fix that
 * does not weaken the auth. It downloads the part up front rather than
 * streaming it, which for a per-answer part of a few seconds is the right
 * trade -- and seeking inside a blob is entirely local, so it is exact.
 *
 * The caller owns the returned URL and must revoke it.
 */
export async function apiObjectUrl(path: string): Promise<string> {
  const token = await getToken();
  const res = await fetch(`${env.apiBaseUrl}${apiPath(path)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`${res.status} fetching media: ${await res.text()}`);
  }
  return URL.createObjectURL(await res.blob());
}
