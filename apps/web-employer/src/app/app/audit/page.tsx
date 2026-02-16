"use client";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export default function AuditViewsPage() {
  const q = useQuery({ queryKey: ["audit_views"], queryFn: () => apiFetch<any[]>("/audit/views?limit=200") });

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">View Audit</div>
        <div className="text-sm text-black/60">Who viewed what when (GET requests logged by middleware).</div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="mt-3 space-y-2">
          {(q.data ?? []).map((e) => (
            <div key={e.id} className="rounded-xl border border-black/10 p-3">
              <div className="font-medium">{e.route}</div>
              <div className="text-xs text-black/60">actor: {e.actor_role ?? "—"} • {e.actor_user_id ?? "—"}</div>
              <div className="text-xs text-black/60">entity: {e.entity_type ?? "—"} • {e.entity_id ?? "—"}</div>
              <div className="text-xs text-black/50">{new Date(e.created_at).toLocaleString()}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
