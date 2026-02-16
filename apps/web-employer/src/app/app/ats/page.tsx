"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

export default function ATSPage() {
  const providersQ = useQuery({ queryKey: ["ats_providers"], queryFn: () => apiFetch<{ providers: string[] }>("/ats/providers") });
  const jobsQ = useQuery({ queryKey: ["jobs"], queryFn: () => apiFetch<any[]>("/recruiting/jobs") });

  const [provider, setProvider] = useState("linkedin");
  const [jobId, setJobId] = useState("");

  async function publish() {
    await apiPost("/ats/publish", { provider, job_posting_id: jobId });
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">ATS Syndication</div>
        <div className="text-sm text-black/60">Connectors scaffolded; wire credentials to enable real publishing.</div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4 space-y-3">
        <Input label="Provider" value={provider} onChange={(e) => setProvider(e.target.value)} />
        <div className="text-xs text-black/50">Available: {(providersQ.data?.providers ?? []).join(", ")}</div>
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
