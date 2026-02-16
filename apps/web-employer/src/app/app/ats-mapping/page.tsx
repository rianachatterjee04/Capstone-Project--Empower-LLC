"use client";
import { useEffect, useState } from "react";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

export default function ATSMappingPage() {
  const [provider, setProvider] = useState("greenhouse");
  const [mappings, setMappings] = useState<any[]>([]);
  const [ext, setExt] = useState("");
  const [inte, setInte] = useState("Phone Screen");

  async function load() {
    const r = await apiFetch(`/ats/mappings/${provider}`);
    setMappings(r.items || []);
  }

  async function save() {
    await apiPost(`/ats/mappings/${provider}`, { external_stage: ext, internal_stage: inte });
    setExt("");
    await load();
  }

  async function replay() {
    await apiPost(`/integrations/replay/${provider}`, {});
    alert("Replay started (Temporal workflow).");
  }

  useEffect(() => { load(); }, [provider]);

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">ATS Mapping + AI Screening</div>
        <div className="text-sm text-black/60">
          Map external stages to your internal pipeline, then AI-screen candidates with decision lineage.
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4 space-y-3">
        <Input label="Provider (greenhouse or lever)" value={provider} onChange={(e) => setProvider(e.target.value)} />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Input label="External stage" value={ext} onChange={(e) => setExt(e.target.value)} />
          <Input label="Internal stage" value={inte} onChange={(e) => setInte(e.target.value)} />
        </div>
        <div className="flex gap-2">
          <Button onClick={save}>Save mapping</Button>
          <Button onClick={replay}>Replay events</Button>
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="text-sm font-semibold">Current mappings</div>
        <pre className="mt-3 text-xs bg-black/5 rounded-xl p-3 overflow-auto">{JSON.stringify(mappings, null, 2)}</pre>
      </div>
    </div>
  );
}
