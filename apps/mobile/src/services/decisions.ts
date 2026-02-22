const apiBase = process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

export async function respondToDecision(id: string, action: string): Promise<void> {
  await fetch(`${apiBase}/decisions/respond`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, action }),
  });
}
