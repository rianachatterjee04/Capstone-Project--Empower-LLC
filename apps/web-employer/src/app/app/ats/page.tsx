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
  const [status, setStatus] = useState<"idle" | "success" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");

  async function publish() {
    setStatus("idle");
    try {
      await apiPost("/ats/publish", { provider, job_id: jobId || undefined });
      setStatus("success");
      setTimeout(() => setStatus("idle"), 3000);
    } catch (e: any) {
      setStatus("error");
      setErrorMsg(e?.message ?? "Something went wrong");
      setTimeout(() => setStatus("idle"), 4000);
    }
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
        <div className="flex items-center gap-3">
          <Button onClick={publish}>Publish</Button>
          {status === "success" && (
            <span className="text-sm text-green-600 font-medium">✓ Published to {provider}</span>
          )}
          {status === "error" && (
            <span className="text-sm text-red-600 font-medium">✗ {errorMsg}</span>
          )}
        </div>
        <div className="text-xs text-black/50">Tip: create a job in Recruiting, then paste its ID here.</div>
      </div>
      <div className="rounded-2xl border border-black/10 p-4">
        <div className="text-sm font-semibold">Recent jobs</div>
        <div className="mt-3 space-y-2">
          {(jobsQ.data ?? []).map((j) => (
            <div
              key={j.id}
              className="rounded-xl border border-black/10 p-3 cursor-pointer hover:border-black/20 transition-colors"
              onClick={() => setJobId(j.id)}
            >
              <div className="font-medium">{j.title}</div>
              <div className="text-xs text-black/60">{j.id}</div>
            </div>
          ))}
        </div>
        {(jobsQ.data ?? []).length > 0 && (
          <div className="text-xs text-black/40 mt-2">Click a job to auto-fill the ID above.</div>
        )}
      </div>
    </div>
  );
}