"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

/**
 * WHY THE RETRY POLICY IS SPELLED OUT
 * The default is three retries with exponential backoff, applied to every
 * failure regardless of cause. A 404 will never become a 200, so retrying one
 * three times buys nothing and costs about seven seconds — during which the
 * page shows its loading state and looks like it is about to work.
 *
 * That is how /app/interviews/live?id=... came to sit on "Loading…" for a real
 * interview the copilot has no record of. The request had already failed; the
 * screen had no way to know yet.
 *
 * So: retry server errors and genuine network failures, where a retry can
 * actually help. Surface client errors immediately, because they are answers,
 * not outages.
 */
function shouldRetry(failureCount: number, error: unknown): boolean {
  const status = (error as { status?: number } | null)?.status;
  if (typeof status === "number" && status >= 400 && status < 500) return false;
  return failureCount < 2;
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { retry: shouldRetry } },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
