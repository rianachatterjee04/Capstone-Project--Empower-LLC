import { getSession, clearSession } from "./session";

export type AppRole = "owner" | "admin" | "hr" | "manager" | "employee";

export async function getUserContext(): Promise<{
  role: AppRole;
  orgId: string | null;
  email: string | null;
}> {
  // The signed-in email personalizes the workspace; the org stays the demo
  // Empower LLC workspace so the real seeded data loads.
  const session = getSession();
  return {
    role: "owner",
    orgId: "11111111-1111-1111-1111-111111111111",
    email: session?.email ?? "dev@local.test",
  };
}

export async function signOut(): Promise<void> {
  if (typeof window !== "undefined") {
    clearSession();
    window.location.href = "/";
  }
}
