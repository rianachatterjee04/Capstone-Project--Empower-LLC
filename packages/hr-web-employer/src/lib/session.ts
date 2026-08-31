// Lightweight session for the People (HR) employer app.
//
// People does not have per-user backend accounts yet, so this login gates
// access to the workspace and validates the shared demo credential on the
// client. Finance and Compliance authenticate against their real backends;
// this keeps People's demo self-contained so it always works during a pitch,
// independent of any backend being awake or an email being confirmed.
//
// To change the demo credential, edit the two constants below (or set the
// matching NEXT_PUBLIC_* env vars at build time).

// The default credential is a neutral, obviously-fake address on a reserved
// TLD. It used to be a real personal gmail account, which meant every copy of
// this repo -- including the one handed to an outside evaluator -- shipped one
// person's actual email address as a login hint. Nothing about the demo needed
// that address; it was only ever a string to compare against.
const DEMO_EMAIL = (process.env.NEXT_PUBLIC_DEMO_EMAIL || "demo@fintra-hr.test").toLowerCase();
const DEMO_PASSWORD = process.env.NEXT_PUBLIC_DEMO_PASSWORD || "FintraHrDemo2026!";

const SESSION_KEY = "hr_session";

export type HrSession = { email: string; at: number };

export function signInDemo(email: string, password: string): boolean {
  const ok = email.trim().toLowerCase() === DEMO_EMAIL && password === DEMO_PASSWORD;
  if (ok && typeof window !== "undefined") {
    const session: HrSession = { email: email.trim(), at: Date.now() };
    localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  }
  return ok;
}

export function getSession(): HrSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    return raw ? (JSON.parse(raw) as HrSession) : null;
  } catch {
    return null;
  }
}

export function isSignedIn(): boolean {
  return getSession() !== null;
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(SESSION_KEY);
  localStorage.removeItem("access_token");
}
