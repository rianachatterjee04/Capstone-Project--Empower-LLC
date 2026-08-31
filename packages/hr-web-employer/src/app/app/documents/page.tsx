"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { PageHeader, Surface, SectionTitle, StatusPill, EmptyState } from "@/components/ds";

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
    setMsg(`Registered document ${reg.id}. The record and its storage pointer are saved; the file itself has not been uploaded.`);
    await qc.invalidateQueries({ queryKey: ["documents"] });
  }

  const docs = q.data ?? [];

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="People"
        title="Documents"
        subtitle="Document records and the HR verification queue. Files are tracked by storage pointer — uploading the file itself is not connected yet."
      />

      <Surface className="space-y-3">
        <SectionTitle title="Register a document" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Input label="Category" value={category} onChange={(e) => setCategory(e.target.value)} />
          <Input label="Filename" value={filename} onChange={(e) => setFilename(e.target.value)} />
          <Input label="Employee ID (optional)" value={employeeId} onChange={(e) => setEmployeeId(e.target.value)} />
        </div>
        <Button onClick={presign}>Presign + Register</Button>
        {msg ? <div className="text-sm text-body">{msg}</div> : null}
      </Surface>

      <Surface>
        <SectionTitle title="Recent documents" description={`${docs.length} total`} />
        {q.isLoading ? <div className="mt-3 text-sm text-muted">Loading…</div> : null}
        {q.error ? <div className="mt-3 text-sm text-danger-fg">{(q.error as Error).message}</div> : null}
        {!q.isLoading && docs.length === 0 ? (
          <EmptyState title="No documents yet" description="Register a document above to start the verification queue." />
        ) : (
          <div className="mt-4 space-y-2">
            {docs.map((d) => (
              <div key={d.id} className="rounded-md border border-line bg-canvas p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="font-medium text-sm text-ink">{d.category}</div>
                  <StatusPill value={d.status} />
                </div>
                <div className="text-xs text-muted mt-1">{d.storage_bucket}/{d.storage_path}</div>
                <div className="text-xs text-faint">{new Date(d.created_at).toLocaleString()}</div>
              </div>
            ))}
          </div>
        )}
      </Surface>
    </div>
  );
}
