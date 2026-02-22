import { apiPost } from "@/lib/api";

export async function respondToDecision(id: string, action: string): Promise<void> {
  await apiPost("/decisions/respond", { id, action });
}
