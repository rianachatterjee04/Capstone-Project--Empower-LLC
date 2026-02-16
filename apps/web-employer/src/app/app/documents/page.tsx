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
  const [employeeId, setEmployeeId] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const q = useQuery({ queryKey: ["documents"], queryFn: () => apiFetch<Doc[]>("/documents") });

  async function presign() {
    setMsg(null);
    const presigned = await apiPost<{bucket:string; path:string}>("/documents/presign", { category, filename, employee_id: employeeId || null });
    // In production you'd upload to Supabase Storage using signed URL. Here we just register the pointer.
    const reg = await apiPost<{id:string}>("/documents", { category, storage_bucket: presigned.bucket, storage_path: presigned.path, status: "uploaded", employee_id: employeeId || null });
    setMsg(`Registered document ${reg.id} (upload wiring is stubbed).`);
    await qc.invalidateQueries({ queryKey: ["documents"] });
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Documents</div>
        <div className="text-sm text-black/60">Secure storage pointers + HR verification queue (upload wiring stubbed).</div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4 space-y-3">
        <div className="text-sm font-semibold">Register a document</div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Input label="Category" value={category} onChange={(e) => setCategory(e.target.value)} />
          <Input label="Filename" value={filename} onChange={(e) => setFilename(e.target.value)} />
          <Input label="Employee ID (optional)" value={employeeId} onChange={(e) => setEmployeeId(e.target.value)} />
        </div>
        <Button onClick={presign}>Presign + Register</Button>
        {msg ? <div className="text-sm text-black/70">{msg}</div> : null}
      </div>

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="text-sm font-semibold">Recent documents</div>
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
