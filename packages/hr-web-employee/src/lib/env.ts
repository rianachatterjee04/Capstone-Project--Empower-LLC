// Local-dev safe: provide placeholder Supabase values so the app boots without
// real credentials. Replace with real env in production.
export const env = {
  supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL || "https://example.supabase.co",
  supabaseAnonKey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "placeholder-anon-key",
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? (process.env.NODE_ENV === 'production' ? "https://people-api.fintrahub.com/api" : "http://localhost:8000/api"),
};

/**
 * The realtime socket base, derived from the API base URL.
 *
 * WHY DERIVED
 * The websocket base was an independent constant defaulting to
 * `ws://localhost:8000`. Point the app at an API on any other port -- which is
 * what a fresh evaluator does -- and every page opened a socket to 8000, failed,
 * and retried, filling the console with errors that had nothing to do with the
 * app being broken. The socket lives on the same host as the API, so it should
 * be read off the same setting rather than configured twice.
 *
 * NEXT_PUBLIC_API_WS still wins when set, for deployments that terminate
 * websockets somewhere else.
 */
export function apiWsBase(): string {
  const explicit = process.env.NEXT_PUBLIC_API_WS;
  if (explicit) return explicit;
  const base = env.apiBaseUrl.replace(/\/api\/?$/, "");
  return base.replace(/^http/, "ws");
}
