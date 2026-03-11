import { apiPost } from "../api";

const DEV_TOKEN = "dev:11111111-1111-1111-1111-111111111111:owner:dev@local.test:22222222-2222-2222-2222-222222222222";

export async function respondToDecision(id: string, action: string): Promise<void> {
  await apiPost("/decisions/respond", { id, action }, DEV_TOKEN);
}
