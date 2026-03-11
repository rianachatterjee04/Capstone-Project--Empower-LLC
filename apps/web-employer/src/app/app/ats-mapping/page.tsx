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
      <div className="text-2xl font-semibold">ATS Stage Mapping</div>

      <div className="flex gap-3">
        <select
          className="border rounded px-3 py-2"
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
        >
          <option value="greenhouse">Greenhouse</option>
          <option value="lever">Lever</option>
        </select>

        <input
          className="border rounded px-3 py-2"
          placeholder="External stage"
          value={externalStage}
          onChange={(e) => setExternalStage(e.target.value)}
        />

        <input
          className="border rounded px-3 py-2"
          placeholder="Internal stage"
          value={internalStage}
          onChange={(e) => setInternalStage(e.target.value)}
        />

        <button
          className="border rounded px-4 py-2"
          onClick={save}
        >
          Save
        </button>
      </div>

      <div className="space-y-2">
        {mappings.map((m, i) => (
          <div key={`${m.external_stage}-${m.internal_stage}-${i}`} className="border rounded p-3">
            <div><strong>External:</strong> {m.external_stage}</div>
            <div><strong>Internal:</strong> {m.internal_stage}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
