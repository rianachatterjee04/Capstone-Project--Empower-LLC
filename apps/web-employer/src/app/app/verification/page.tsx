"use client";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";

export default function VerificationPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["verify_queue"], queryFn: () => apiFetch<any[]>("/verification/queue") });

  async function setStatus(id: string, status: string) {
    await apiPost(`/verification/documents/${id}/verify`, { status });
    await qc.invalidateQueries({ queryKey: ["verify_queue"] });
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">HR Verification Queue</div>
        <div className="text-sm text-black/60">Verify/reject uploaded documents. Signed upload works when SUPABASE_SERVICE_ROLE_KEY is set.</div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="space-y-2">
          {(q.data ?? []).map((d) => (
            <div key={d.id} className="rounded-xl border border-black/10 p-3 flex items-center justify-between">
              <div>
                <div className="font-medium">{d.category} • {d.status}</div>
                <div className="text-xs text-black/60">{d.storage_bucket}/{d.storage_path}</div>
              </div>
              <div className="flex gap-2">
                <Button onClick={() => setStatus(d.id, "in_review")}>In review</Button>
                <Button onClick={() => setStatus(d.id, "verified")}>Verify</Button>
                <Button onClick={() => setStatus(d.id, "rejected")}>Reject</Button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
