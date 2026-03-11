export type AppRole = "owner" | "admin" | "hr" | "manager" | "employee";

export async function getUserContext(): Promise<{
  role: AppRole;
  orgId: string | null;
  email: string | null;
}> {
  return {
    role: "owner",
    orgId: "11111111-1111-1111-1111-111111111111",
    email: "dev@local.test",
  };
}

export async function signOut(): Promise<void> {
  if (typeof window !== "undefined") {
    localStorage.removeItem("access_token");
    window.location.href = "/";
  }
}
