// The Supabase browser client is deliberately NOT constructed in this build.
// Auth runs through the app's own dev context (see `lib/auth`), and importing
// the real client would pull a public anon key into every bundle.
//
// It is still exported, typed, and checked for, so the one caller that prefers
// a real session token (`lib/useLiveData`) keeps its preference order intact
// and compiles. Typing it `null` alone made TypeScript narrow the guarded
// branch to `never`, so `supabase.auth` was a build error rather than dead
// code -- which is how `tsc --noEmit` came to fail on a file nobody had
// touched.
export type SupabaseLike = {
  auth: {
    getSession(): Promise<{
      data: { session: { access_token?: string | null } | null };
    }>;
  };
};

export const supabase: SupabaseLike | null = null;
