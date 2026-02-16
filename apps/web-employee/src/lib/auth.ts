import { supabase } from "./supabaseClient";
export type AppRole = "owner" | "admin" | "hr" | "manager" | "employee";

export async function getUserContext(): Promise<{ role: AppRole; orgId: string | null; email: string | null }> {
  const { data } = await supabase.auth.getSession();
  const user: any = data.session?.user ?? null;
  const role = (user?.app_metadata?.role || user?.user_metadata?.role || "employee") as AppRole;
  const orgId = (user?.app_metadata?.org_id || user?.user_metadata?.org_id || null) as string | null;
  const email = (user?.email ?? null) as string | null;
  return { role, orgId, email };
}

export async function signOut() {
  await supabase.auth.signOut();
  window.location.href = "/";
}
