"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

type AtsProviderRow = { provider: string; connected: boolean };
type AtsProvidersResponse = { items: AtsProviderRow[] };

export default function ATSPage() {
  const providersQ = useQuery({
    queryKey: ["ats_providers"],
    queryFn: () => apiFetch<AtsProvidersResponse>("/ats/providers"),
  });
  const jobsQ = useQuery({ queryKey: ["jobs"], queryFn: () => apiFetch<any[]>("/recruiting/jobs") });

  const [provider, setProvider] = useState<"greenhouse" | "lever">("greenhouse");
  const [jobId, setJobId] = useState("");

  async function publish() {
    await apiPost("/ats/publish", { provider, job_id: jobId || undefined });
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">ATS Syndication</div>
        <div className="text-sm text-black/60">Connectors scaffolded; wire credentials to enable real publishing.</div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4 space-y-3">
        <label className="block text-sm font-medium text-black/80">Provider</label>
        <select
          className="mt-1 w-full max-w-md rounded-xl border border-black/15 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/20"
          value={provider}
          onChange={(e) => setProvider(e.target.value as "greenhouse" | "lever")}
        >
          <option value="greenhouse">Greenhouse</option>
          <option value="lever">Lever</option>
        </select>
        <div className="text-xs text-black/50">
          Connection status:{" "}
          {(providersQ.data?.items ?? [])
            .map((p) => `${p.provider}${p.connected ? " (connected)" : ""}`)
            .join(" · ") || "loading…"}
        </div>
        <Input label="Job posting ID" value={jobId} onChange={(e) => setJobId(e.target.value)} />
        <Button onClick={publish}>Publish</Button>
        <div className="text-xs text-black/50">Tip: create a job in Recruiting, then paste its ID here.</div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="text-sm font-semibold">Recent jobs</div>
        <div className="mt-3 space-y-2">
          {(jobsQ.data ?? []).map((j) => (
            <div key={j.id} className="rounded-xl border border-black/10 p-3">
              <div className="font-medium">{j.title}</div>
              <div className="text-xs text-black/60">{j.id}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
