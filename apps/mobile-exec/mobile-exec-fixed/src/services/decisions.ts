import { apiPost } from "../api";

export async function respondToDecision(id: string, action: string, token?: string): Promise<void> {
  await apiPost("/decisions/respond", { id, action }, token);
}
