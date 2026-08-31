"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";

export default function VerificationPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["verify_queue"], queryFn: () => apiFetch<any[]>("/verification/queue") });
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function setStatus(id: string, status: string) {
    setError(null);
    setBusyId(id);
    try {
      await apiPost(`/verification/documents/${id}/verify`, { status });
      await qc.invalidateQueries({ queryKey: ["verify_queue"] });
    } catch (e) {
      setError((e as Error).message || "Update failed");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">HR Verification Queue</div>
        <div className="text-sm text-black/60">Verify/reject uploaded documents. Signed upload works when SUPABASE_SERVICE_ROLE_KEY is set.</div>
      </div>

      {error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>
      ) : null}

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="space-y-2">
          {(q.data ?? []).map((d) => (
            <div key={d.id} className="rounded-xl border border-black/10 p-3 flex items-center justify-between">
              <div>
                <div className="font-medium">{d.category} • {d.status}</div>
                <div className="text-xs text-black/60">{d.storage_bucket}/{d.storage_path}</div>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  disabled={busyId === d.id}
                  onClick={() => setStatus(d.id, "in_review")}
                >
                  In review
                </Button>
                <Button disabled={busyId === d.id} onClick={() => setStatus(d.id, "verified")}>
                  Verify
                </Button>
                <Button
                  variant="danger"
                  disabled={busyId === d.id}
                  onClick={() => setStatus(d.id, "rejected")}
                >
                  Reject
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
