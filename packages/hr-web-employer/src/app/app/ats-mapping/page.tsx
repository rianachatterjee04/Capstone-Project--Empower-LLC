"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch, apiPost } from "@/lib/api";

type Mapping = {
  external_stage: string;
  internal_stage: string;
};

type MappingsResponse = {
  items: Mapping[];
};

export default function ATSMappingPage() {
  const [provider, setProvider] = useState("greenhouse");
  const [externalStage, setExternalStage] = useState("");
  const [internalStage, setInternalStage] = useState("");
  const [mappings, setMappings] = useState<Mapping[]>([]);

  const load = useCallback(async () => {
    const r = await apiFetch<MappingsResponse>(`/ats/mappings/${provider}`);
    setMappings(r.items || []);
  }, [provider]);

  useEffect(() => {
    load();
  }, [load]);

  async function save() {
    await apiPost(`/ats/mappings/${provider}`, {
      external_stage: externalStage,
      internal_stage: internalStage,
    });

    setExternalStage("");
    setInternalStage("");
    await load();
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">ATS Stage Mapping</div>
        <div className="mt-1 text-sm text-black/50">Map external ATS stages to internal pipeline stages</div>
      </div>

      <div className="flex gap-3">
        <select
          className="rounded-xl border border-black/15 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/20"
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
        >
          <option value="greenhouse">Greenhouse</option>
          <option value="lever">Lever</option>
        </select>

        <input
          className="rounded-xl border border-black/15 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/20"
          placeholder="External stage"
          value={externalStage}
          onChange={(e) => setExternalStage(e.target.value)}
        />

        <input
          className="rounded-xl border border-black/15 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/20"
          placeholder="Internal stage"
          value={internalStage}
          onChange={(e) => setInternalStage(e.target.value)}
        />

        <button
          className="rounded-xl border border-black/15 px-4 py-2 text-sm font-medium hover:bg-black/5 transition"
          onClick={save}
        >
          Save
        </button>
      </div>

      <div className="space-y-2">
        {mappings.map((m, i) => (
          <div key={`${m.external_stage}-${m.internal_stage}-${i}`} className="rounded-xl border border-black/10 p-3">
            <div><strong>External:</strong> {m.external_stage}</div>
            <div><strong>Internal:</strong> {m.internal_stage}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
