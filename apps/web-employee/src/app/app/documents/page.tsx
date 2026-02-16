"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

type Doc = { id: string; category: string; storage_bucket: string; storage_path: string; status: string; created_at: string; employee_id?: string | null };

export default function DocumentsPage() {
  const qc = useQueryClient();
  const [category, setCategory] = useState("i9");
  const [filename, setFilename] = useState("passport.png");
  const [msg, setMsg] = useState<string | null>(null);

  const q = useQuery({ queryKey: ["documents"], queryFn: () => apiFetch<Doc[]>("/documents") });

  async function presign() {
    setMsg(null);
    const presigned = await apiPost<{bucket:string; path:string}>("/documents/presign", { category, filename });
    const reg = await apiPost<{id:string}>("/documents", { category, storage_bucket: presigned.bucket, storage_path: presigned.path, status: "uploaded" });
    setMsg(`Registered document ${reg.id}. (Upload wiring is stubbed in this MVP.)`);
    await qc.invalidateQueries({ queryKey: ["documents"] });
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Documents</div>
        <div className="text-sm text-black/60">Upload + verification (stubbed). Your HR team can verify and track expiration.</div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4 space-y-3">
        <div className="text-sm font-semibold">Add document</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Input label="Category" value={category} onChange={(e) => setCategory(e.target.value)} />
          <Input label="Filename" value={filename} onChange={(e) => setFilename(e.target.value)} />
        </div>
        <Button onClick={presign}>Presign + Register</Button>
        {msg ? <div className="text-sm text-black/70">{msg}</div> : null}
      </div>

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="text-sm font-semibold">My documents (RLS filtered)</div>
        {q.isLoading ? <div className="mt-3">Loading…</div> : null}
        {q.error ? <div className="mt-3 text-red-600">{(q.error as Error).message}</div> : null}
        <div className="mt-4 space-y-2">
          {(q.data ?? []).map((d) => (
            <div key={d.id} className="rounded-xl border border-black/10 p-3">
              <div className="font-medium">{d.category} • {d.status}</div>
              <div className="text-xs text-black/60">{d.storage_bucket}/{d.storage_path}</div>
              <div className="text-xs text-black/50">{new Date(d.created_at).toLocaleString()}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
